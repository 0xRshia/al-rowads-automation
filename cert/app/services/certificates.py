from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from app.config import DEFAULT_PLACEHOLDER


DOCUMENT_XML = "word/document.xml"
PDF_CONVERSION_TIMEOUT_SECONDS = 60
PDF_CONVERSION_PER_FILE_TIMEOUT_SECONDS = 15
FONT_CACHE_TIMEOUT_SECONDS = 30
FONT_MATCH_TIMEOUT_SECONDS = 15
EMU_PER_POINT = 12700
TWIPS_PER_POINT = 20

XML_NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
}


class CertificateGenerationError(RuntimeError):
    """Raised when certificate generation cannot complete safely."""


@dataclass(frozen=True)
class FastPdfTemplate:
    background_image: bytes
    page_width: float
    page_height: float
    textbox_x: float
    textbox_y: float
    textbox_width: float
    textbox_height: float
    inset_left: float
    inset_top: float
    inset_right: float
    inset_bottom: float
    font_size: float


def generate_certificates(
    names_file: str | Path,
    output_dir: str | Path = "output",
    template_path: str | Path = "Certificate.docx",
    font_path: str | Path = "AbarHigh-SemiBold.ttf",
    placeholder: str = DEFAULT_PLACEHOLDER,
) -> list[Path]:
    """Generate one PDF certificate for each non-empty line in names_file."""
    names_path = Path(names_file)
    output_path = Path(output_dir)
    template = Path(template_path)
    font = Path(font_path)

    _require_file(names_path, "names file")
    _require_file(template, "certificate template")
    _require_file(font, "font file")

    names = load_names(names_path)
    output_path.mkdir(parents=True, exist_ok=True)

    fast_template = _load_fast_pdf_template(template, placeholder)
    if fast_template is not None:
        try:
            return _generate_fast_pdf_certificates(
                names=names,
                output_path=output_path,
                font_path=font,
                template=fast_template,
            )
        except Exception:
            # Keep LibreOffice as the correctness fallback for unsupported fonts/templates.
            pass

    libreoffice = _find_libreoffice()
    generated_pdfs: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="certificates-") as temporary_directory:
        work_dir = Path(temporary_directory)
        conversion_dir = work_dir / "pdf"
        conversion_dir.mkdir()
        env = _prepare_font_environment(font, work_dir)
        font_family = env["CERTIFICATE_FONT_FAMILY"]
        used_pdf_names: set[str] = set()
        pending_conversions: list[tuple[Path, Path]] = []

        for index, name in enumerate(names, start=1):
            pdf_name = _unique_pdf_name(name, used_pdf_names, output_path)
            docx_path = work_dir / f"certificate_{index:04d}.docx"
            final_pdf = output_path / pdf_name

            _write_docx_with_name(template, docx_path, placeholder, name, font_family)
            pending_conversions.append((docx_path, final_pdf))

        converted_pdfs = _convert_docx_files_to_pdf(
            docx_paths=[docx_path for docx_path, _final_pdf in pending_conversions],
            output_dir=conversion_dir,
            libreoffice=libreoffice,
            env=env,
            work_dir=work_dir,
        )

        for docx_path, final_pdf in pending_conversions:
            converted_pdf = converted_pdfs[docx_path]

            if not converted_pdf.exists():
                raise CertificateGenerationError(
                    f"LibreOffice did not create the expected PDF for {docx_path.name}."
                )

            converted_pdf.replace(final_pdf)
            generated_pdfs.append(final_pdf)

    return generated_pdfs


def load_names(names_file: Path) -> list[str]:
    names = [
        line.strip()
        for line in names_file.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not names:
        raise CertificateGenerationError(f"No names found in {names_file}.")
    return names


def create_certificates_zip(pdf_paths: list[Path], output_path: Path) -> Path:
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for pdf_path in pdf_paths:
            archive.write(pdf_path, arcname=pdf_path.name)
    return output_path


def _require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {description}: {path}")


def _find_libreoffice() -> str:
    for command in ("soffice", "libreoffice"):
        executable = shutil.which(command)
        if executable:
            return executable
    raise CertificateGenerationError(
        "LibreOffice was not found on PATH. Install LibreOffice and ensure "
        "`soffice` or `libreoffice` is available."
    )


def _prepare_font_environment(font_path: Path, work_dir: Path) -> dict[str, str]:
    font_dir = work_dir / ".local" / "share" / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    copied_font = font_dir / font_path.name
    shutil.copy2(font_path, copied_font)

    env = os.environ.copy()
    env["HOME"] = str(work_dir)
    env["XDG_DATA_HOME"] = str(work_dir / ".local" / "share")
    env["XDG_CACHE_HOME"] = str(work_dir / ".cache")
    env["XDG_CONFIG_HOME"] = str(work_dir / ".config")
    env["FONTCONFIG_FILE"] = str(_write_fontconfig_file(work_dir, font_dir))

    _run_checked(
        ["fc-cache", "-f", str(font_dir)],
        env=env,
        timeout=FONT_CACHE_TIMEOUT_SECONDS,
        error_prefix="Unable to refresh the temporary font cache",
    )
    font_names = _font_query_names(copied_font, env)
    _verify_font_is_available(copied_font, env, font_names)
    env["CERTIFICATE_FONT_FAMILY"] = font_names[0]
    return env


def _write_fontconfig_file(work_dir: Path, font_dir: Path) -> Path:
    cache_dir = work_dir / ".cache" / "fontconfig"
    cache_dir.mkdir(parents=True, exist_ok=True)
    config_path = work_dir / "fonts.conf"
    config_path.write_text(
        "\n".join(
            [
                '<?xml version="1.0"?>',
                '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">',
                "<fontconfig>",
                f"  <dir>{escape(str(font_dir))}</dir>",
                '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>',
                f"  <cachedir>{escape(str(cache_dir))}</cachedir>",
                "</fontconfig>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _verify_font_is_available(
    copied_font: Path,
    env: dict[str, str],
    font_names: list[str] | None = None,
) -> None:
    font_names = font_names or _font_query_names(copied_font, env)
    copied_font_path = copied_font.resolve()
    match_outputs: list[str] = []

    for font_name in font_names:
        font_match = _run_checked(
            ["fc-match", "--format", "%{file}\n", font_name],
            env=env,
            timeout=FONT_MATCH_TIMEOUT_SECONDS,
            error_prefix=f"Unable to verify uploaded font family {font_name!r}",
        )
        matched_path = Path(font_match.stdout.strip())
        match_outputs.append(f"{font_name}: {font_match.stdout.strip()}")
        if matched_path.exists() and matched_path.resolve() == copied_font_path:
            return

    raise CertificateGenerationError(
        "Unable to verify the uploaded font: Fontconfig did not select the "
        f"uploaded file {copied_font.name}. Matches were: "
        + "; ".join(match_outputs)
    )


def _font_query_names(font_path: Path, env: dict[str, str]) -> list[str]:
    font_scan = _run_checked(
        ["fc-scan", "--format", "%{family}\n%{fullname}\n%{postscriptname}\n", str(font_path)],
        env=env,
        timeout=FONT_MATCH_TIMEOUT_SECONDS,
        error_prefix=f"Unable to read font metadata from {font_path.name}",
    )
    names: list[str] = []
    seen: set[str] = set()
    for line in font_scan.stdout.splitlines():
        for name in line.split(","):
            clean_name = name.strip()
            if clean_name and clean_name not in seen:
                seen.add(clean_name)
                names.append(clean_name)
    if not names:
        raise CertificateGenerationError(
            f"Unable to read any font family names from {font_path.name}."
        )
    return names


def _generate_fast_pdf_certificates(
    names: list[str],
    output_path: Path,
    font_path: Path,
    template: FastPdfTemplate,
) -> list[Path]:
    from arabic_reshaper import reshape
    from bidi.algorithm import get_display
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font_name = f"certificate-font-{abs(hash(font_path.resolve()))}"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))

    generated_pdfs: list[Path] = []
    used_pdf_names: set[str] = set()
    image = ImageReader(BytesIO(template.background_image))

    with tempfile.TemporaryDirectory(prefix="certificates-fast-") as temporary_directory:
        work_dir = Path(temporary_directory)
        pending_outputs: list[tuple[Path, Path]] = []

        for name in names:
            pdf_name = _unique_pdf_name(name, used_pdf_names, output_path)
            final_pdf = output_path / pdf_name
            temporary_pdf = work_dir / pdf_name
            shaped_name = get_display(reshape(name))

            _write_fast_pdf(
                output_pdf=temporary_pdf,
                image=image,
                template=template,
                font_name=font_name,
                text=shaped_name,
                pdfmetrics=pdfmetrics,
                canvas_module=canvas,
            )
            pending_outputs.append((temporary_pdf, final_pdf))

        for temporary_pdf, final_pdf in pending_outputs:
            temporary_pdf.replace(final_pdf)
            generated_pdfs.append(final_pdf)

    return generated_pdfs


def _write_fast_pdf(
    output_pdf: Path,
    image,
    template: FastPdfTemplate,
    font_name: str,
    text: str,
    pdfmetrics,
    canvas_module,
) -> None:
    page_size = (template.page_width, template.page_height)
    pdf = canvas_module.Canvas(str(output_pdf), pagesize=page_size)
    pdf.drawImage(
        image,
        0,
        0,
        width=template.page_width,
        height=template.page_height,
        preserveAspectRatio=False,
        mask="auto",
    )

    content_x = template.textbox_x + template.inset_left
    content_width = template.textbox_width - template.inset_left - template.inset_right
    content_height = template.textbox_height - template.inset_top - template.inset_bottom
    font_size = _fit_text_size(text, font_name, template.font_size, content_width, pdfmetrics)

    ascent, descent = pdfmetrics.getAscentDescent(font_name, font_size)
    text_height = ascent - descent
    content_bottom = (
        template.page_height
        - template.textbox_y
        - template.textbox_height
        + template.inset_bottom
    )
    baseline_y = content_bottom + ((content_height - text_height) / 2) - descent

    pdf.setFont(font_name, font_size)
    pdf.drawCentredString(content_x + (content_width / 2), baseline_y, text)
    pdf.showPage()
    pdf.save()


def _fit_text_size(
    text: str,
    font_name: str,
    font_size: float,
    max_width: float,
    pdfmetrics,
) -> float:
    while font_size > 12 and pdfmetrics.stringWidth(text, font_name, font_size) > max_width:
        font_size -= 1
    return font_size


def _load_fast_pdf_template(template_path: Path, placeholder: str) -> FastPdfTemplate | None:
    try:
        with zipfile.ZipFile(template_path, "r") as archive:
            document_xml = archive.read(DOCUMENT_XML)
            document_root = ElementTree.fromstring(document_xml)
            text_anchor = _find_placeholder_anchor(document_root, placeholder)
            if text_anchor is None:
                return None

            page_width, page_height = _read_page_size(document_root)
            margin_left, margin_top = _read_page_margins(document_root)
            background_image = _read_background_image(archive, document_root)
            if background_image is None:
                return None

            textbox_x = _read_anchor_position(
                text_anchor,
                axis="H",
                margin_offset=margin_left,
            )
            textbox_y = _read_anchor_position(
                text_anchor,
                axis="V",
                margin_offset=margin_top,
            )
            textbox_width, textbox_height = _read_anchor_extent(text_anchor)
            inset_left, inset_top, inset_right, inset_bottom = _read_textbox_insets(text_anchor)
            font_size = _read_placeholder_font_size(text_anchor, placeholder)
    except (KeyError, ElementTree.ParseError, zipfile.BadZipFile):
        return None

    if textbox_width <= 0 or textbox_height <= 0:
        return None

    return FastPdfTemplate(
        background_image=background_image,
        page_width=page_width,
        page_height=page_height,
        textbox_x=textbox_x,
        textbox_y=textbox_y,
        textbox_width=textbox_width,
        textbox_height=textbox_height,
        inset_left=inset_left,
        inset_top=inset_top,
        inset_right=inset_right,
        inset_bottom=inset_bottom,
        font_size=font_size,
    )


def _find_placeholder_anchor(document_root: ElementTree.Element, placeholder: str):
    for anchor in document_root.findall(".//wp:anchor", XML_NAMESPACES):
        if placeholder in "".join(anchor.itertext()):
            return anchor
    return None


def _read_page_size(document_root: ElementTree.Element) -> tuple[float, float]:
    page_size = document_root.find(".//w:sectPr/w:pgSz", XML_NAMESPACES)
    if page_size is None:
        return 841.9, 595.3
    width = _twips_to_points(int(page_size.attrib[_w_attr("w")]))
    height = _twips_to_points(int(page_size.attrib[_w_attr("h")]))
    return width, height


def _read_page_margins(document_root: ElementTree.Element) -> tuple[float, float]:
    page_margins = document_root.find(".//w:sectPr/w:pgMar", XML_NAMESPACES)
    if page_margins is None:
        return 0, 0
    left = _twips_to_points(int(page_margins.attrib.get(_w_attr("left"), "0")))
    top = _twips_to_points(int(page_margins.attrib.get(_w_attr("top"), "0")))
    return left, top


def _read_background_image(
    archive: zipfile.ZipFile,
    document_root: ElementTree.Element,
) -> bytes | None:
    section = document_root.find(".//w:sectPr", XML_NAMESPACES)
    if section is not None:
        header_reference = section.find("w:headerReference", XML_NAMESPACES)
        if header_reference is not None:
            header_id = header_reference.attrib.get(_r_attr("id"))
            header_path = _relationship_target(
                archive.read("word/_rels/document.xml.rels"),
                header_id,
                "word",
            )
            if header_path:
                image_path = _header_background_image_path(archive, header_path)
                if image_path:
                    return archive.read(image_path)

    for name in archive.namelist():
        if name.startswith("word/media/") and name.lower().endswith((".png", ".jpg", ".jpeg")):
            return archive.read(name)
    return None


def _header_background_image_path(archive: zipfile.ZipFile, header_path: str) -> str | None:
    header_root = ElementTree.fromstring(archive.read(header_path))
    blip = header_root.find(".//a:blip", XML_NAMESPACES)
    if blip is None:
        return None
    image_id = blip.attrib.get(_r_attr("embed"))
    rels_path = _rels_path_for_part(header_path)
    return _relationship_target(archive.read(rels_path), image_id, str(Path(header_path).parent))


def _relationship_target(rels_xml: bytes, rel_id: str | None, base_path: str) -> str | None:
    if rel_id is None:
        return None
    rels_root = ElementTree.fromstring(rels_xml)
    for relationship in rels_root.findall("rel:Relationship", XML_NAMESPACES):
        if relationship.attrib.get("Id") == rel_id:
            target = relationship.attrib["Target"]
            if target.startswith("/"):
                return target.lstrip("/")
            return str((Path(base_path) / target).as_posix())
    return None


def _rels_path_for_part(part_path: str) -> str:
    part = Path(part_path)
    return str(part.parent / "_rels" / f"{part.name}.rels")


def _read_anchor_position(
    anchor: ElementTree.Element,
    axis: str,
    margin_offset: float,
) -> float:
    position = anchor.find(f"wp:position{axis}", XML_NAMESPACES)
    if position is None:
        return margin_offset
    offset = position.find("wp:posOffset", XML_NAMESPACES)
    if offset is None or offset.text is None:
        return margin_offset
    value = _emu_to_points(int(offset.text))
    if position.attrib.get("relativeFrom") in {"margin", "paragraph", "text"}:
        value += margin_offset
    return value


def _read_anchor_extent(anchor: ElementTree.Element) -> tuple[float, float]:
    extent = anchor.find("wp:extent", XML_NAMESPACES)
    if extent is None:
        return 0, 0
    return _emu_to_points(int(extent.attrib["cx"])), _emu_to_points(int(extent.attrib["cy"]))


def _read_textbox_insets(anchor: ElementTree.Element) -> tuple[float, float, float, float]:
    body = anchor.find(".//wps:bodyPr", XML_NAMESPACES)
    if body is None:
        return 0, 0, 0, 0
    return (
        _emu_to_points(int(body.attrib.get("lIns", "0"))),
        _emu_to_points(int(body.attrib.get("tIns", "0"))),
        _emu_to_points(int(body.attrib.get("rIns", "0"))),
        _emu_to_points(int(body.attrib.get("bIns", "0"))),
    )


def _read_placeholder_font_size(anchor: ElementTree.Element, placeholder: str) -> float:
    for paragraph in anchor.findall(".//w:p", XML_NAMESPACES):
        if placeholder not in "".join(paragraph.itertext()):
            continue
        size = paragraph.find(".//w:sz", XML_NAMESPACES)
        if size is not None:
            return int(size.attrib[_w_attr("val")]) / 2
    return 36


def _emu_to_points(value: int) -> float:
    return value / EMU_PER_POINT


def _twips_to_points(value: int) -> float:
    return value / TWIPS_PER_POINT


def _w_attr(name: str) -> str:
    return f"{{{XML_NAMESPACES['w']}}}{name}"


def _r_attr(name: str) -> str:
    return f"{{{XML_NAMESPACES['r']}}}{name}"


def _write_docx_with_name(
    template_path: Path,
    output_docx_path: Path,
    placeholder: str,
    name: str,
    font_family: str | None = None,
) -> None:
    placeholder_xml = escape(placeholder)
    name_xml = escape(name)
    replaced = False

    with zipfile.ZipFile(template_path, "r") as source:
        if DOCUMENT_XML not in source.namelist():
            raise CertificateGenerationError(
                f"{template_path} does not contain {DOCUMENT_XML}."
            )

        with zipfile.ZipFile(output_docx_path, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                content = source.read(item.filename)
                if item.filename == DOCUMENT_XML:
                    document_xml = content.decode("utf-8")
                    if placeholder_xml not in document_xml:
                        raise CertificateGenerationError(
                            f"Placeholder text was not found in {DOCUMENT_XML}: "
                            f"{placeholder}"
                        )
                    if font_family:
                        document_xml = _replace_placeholder_font_family(
                            document_xml,
                            placeholder_xml,
                            font_family,
                        )
                    document_xml = document_xml.replace(placeholder_xml, name_xml)
                    content = document_xml.encode("utf-8")
                    replaced = True
                target.writestr(item, content)

    if not replaced:
        raise CertificateGenerationError(
            f"Placeholder text was not replaced in {output_docx_path}."
        )


def _replace_placeholder_font_family(
    document_xml: str,
    placeholder_xml: str,
    font_family: str,
) -> str:
    font_attr = escape(font_family, {'"': "&quot;"})

    def replace_paragraph(match: re.Match[str]) -> str:
        paragraph = match.group(0)
        if placeholder_xml not in paragraph:
            return paragraph
        return _replace_rfonts_tags(paragraph, font_attr)

    return re.sub(r"<w:p\b.*?</w:p>", replace_paragraph, document_xml, flags=re.DOTALL)


def _replace_rfonts_tags(xml_fragment: str, font_attr: str) -> str:
    def replace_rfonts(match: re.Match[str]) -> str:
        tag = match.group(0)
        for attr_name in ("ascii", "hAnsi", "cs"):
            qualified_attr = f"w:{attr_name}"
            if f"{qualified_attr}=" in tag:
                tag = re.sub(
                    rf'({qualified_attr}=")[^"]*(")',
                    lambda attr_match: f"{attr_match.group(1)}{font_attr}{attr_match.group(2)}",
                    tag,
                )
            else:
                insert_at = -2 if tag.endswith("/>") else -1
                tag = f'{tag[:insert_at]} {qualified_attr}="{font_attr}"{tag[insert_at:]}'
        return tag

    return re.sub(r"<w:rFonts\b[^>]*/?>", replace_rfonts, xml_fragment)


def _convert_docx_to_pdf(
    docx_path: Path,
    output_dir: Path,
    libreoffice: str,
    env: dict[str, str],
) -> Path:
    return _convert_docx_files_to_pdf(
        docx_paths=[docx_path],
        output_dir=output_dir,
        libreoffice=libreoffice,
        env=env,
        work_dir=docx_path.parent,
    )[docx_path]


def _convert_docx_files_to_pdf(
    docx_paths: list[Path],
    output_dir: Path,
    libreoffice: str,
    env: dict[str, str],
    work_dir: Path,
) -> dict[Path, Path]:
    if not docx_paths:
        return {}

    user_installation_dir = work_dir / "libreoffice-profile"
    user_installation_dir.mkdir(parents=True, exist_ok=True)
    command = [
        libreoffice,
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--nodefault",
        "--norestore",
        "--nolockcheck",
        f"-env:UserInstallation={user_installation_dir.resolve().as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        *[str(docx_path) for docx_path in docx_paths],
    ]
    _run_checked(
        command,
        env=env,
        timeout=_pdf_conversion_timeout(len(docx_paths)),
        error_prefix=f"Unable to convert {len(docx_paths)} DOCX file(s) to PDF",
    )
    return {docx_path: output_dir / f"{docx_path.stem}.pdf" for docx_path in docx_paths}


def _pdf_conversion_timeout(file_count: int) -> int:
    return PDF_CONVERSION_TIMEOUT_SECONDS + (
        max(file_count - 1, 0) * PDF_CONVERSION_PER_FILE_TIMEOUT_SECONDS
    )


def _run_checked(
    command: list[str],
    env: dict[str, str],
    timeout: int,
    error_prefix: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise CertificateGenerationError(
            f"{error_prefix}: required command was not found: {command[0]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CertificateGenerationError(
            f"{error_prefix}: command timed out after {timeout} seconds."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout.strip()
        stderr = exc.stderr.strip()
        details = "\n".join(part for part in (stdout, stderr) if part)
        message = f"{error_prefix}: command failed with exit code {exc.returncode}."
        if details:
            message = f"{message}\n{details}"
        raise CertificateGenerationError(message) from exc


def _unique_pdf_name(name: str, used_names: set[str], output_dir: Path | None = None) -> str:
    base = _sanitize_filename(name)
    candidate = f"{base}.pdf"
    suffix = 2

    while candidate in used_names or (
        output_dir is not None and (output_dir / candidate).exists()
    ):
        candidate = f"{base}_{suffix}.pdf"
        suffix += 1

    used_names.add(candidate)
    return candidate


def _sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name.strip())
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = sanitized.strip(" .")
    return sanitized or "certificate"
