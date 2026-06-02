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
from xml.sax.saxutils import escape, unescape

from app.config import DEFAULT_PLACEHOLDER


DOCUMENT_XML = "word/document.xml"
WORD_TEXT_PART_PATTERN = re.compile(
    r"^word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$"
)
WORD_PARAGRAPH_PATTERN = re.compile(r"<w:p\b.*?</w:p>", re.DOTALL)
WORD_RUN_PATTERN = re.compile(r"<w:r\b[^>]*>.*?</w:r>", re.DOTALL)
WORD_TEXT_PATTERN = re.compile(r"(<w:t\b[^>]*>)(.*?)(</w:t>)", re.DOTALL)
RTL_TEXT_PATTERN = re.compile(r"[\u0590-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
PERSIAN_TEXT_PATTERN = re.compile(r"[\u067e\u0686\u0698\u06af\u06cc]")
PDF_CONVERSION_TIMEOUT_SECONDS = 60
PDF_CONVERSION_PER_FILE_TIMEOUT_SECONDS = 15
FONT_CACHE_TIMEOUT_SECONDS = 30
FONT_MATCH_TIMEOUT_SECONDS = 15
EMU_PER_POINT = 12700
TWIPS_PER_POINT = 20
TEXT_MEASUREMENT_SCALE = 4
TEXT_RENDERING_CENTER_CORRECTION_POINTS = -1.0
BACKGROUND_BOX_DETECTION_PADDING_POINTS = 20
MIN_FAST_PDF_FONT_SIZE = 4
CERTIFICATE_TEXT_COLOR = "FFFFFF"
FAST_PDF_TEXT_IMAGE_SCALE = 4

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

    if not placeholder:
        raise CertificateGenerationError("Placeholder cannot be empty.")

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

            _write_fast_pdf(
                output_pdf=temporary_pdf,
                image=image,
                template=template,
                font_name=font_name,
                font_path=font_path,
                text=name,
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
    font_path: Path | None,
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
    content_bottom = (
        template.page_height
        - template.textbox_y
        - template.textbox_height
        + template.inset_bottom
    )

    if font_path is not None and _contains_rtl_text(text):
        text_image = _render_fast_pdf_text_image(
            text=text,
            font_path=font_path,
            font_size=template.font_size,
            max_width=content_width,
            max_height=content_height,
        )
        if text_image is not None:
            from reportlab.lib.utils import ImageReader

            pdf.drawImage(
                ImageReader(BytesIO(text_image)),
                content_x,
                content_bottom,
                width=content_width,
                height=content_height,
                preserveAspectRatio=False,
                mask="auto",
            )
            pdf.showPage()
            pdf.save()
            return

    display_text = _fast_pdf_display_text(text)
    font_size = _fit_text_size(
        display_text,
        font_name,
        template.font_size,
        content_width,
        pdfmetrics,
    )
    baseline_y = _centered_text_baseline_y(
        content_bottom=content_bottom,
        content_height=content_height,
        text=display_text,
        font_path=font_path,
        font_size=font_size,
        font_name=font_name,
        pdfmetrics=pdfmetrics,
    )

    pdf.setFont(font_name, font_size)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.drawCentredString(content_x + (content_width / 2), baseline_y, display_text)
    pdf.showPage()
    pdf.save()


def _centered_text_baseline_y(
    content_bottom: float,
    content_height: float,
    text: str,
    font_path: Path | None,
    font_size: float,
    font_name: str,
    pdfmetrics,
) -> float:
    content_center_y = content_bottom + (content_height / 2)
    return content_center_y + _text_baseline_offset_from_center(
        text=text,
        font_path=font_path,
        font_size=font_size,
        font_name=font_name,
        pdfmetrics=pdfmetrics,
    )


def _text_baseline_offset_from_center(
    text: str,
    font_path: Path | None,
    font_size: float,
    font_name: str,
    pdfmetrics,
) -> float:
    if font_path is not None:
        try:
            from PIL import ImageFont

            measured_size = max(1, round(font_size * TEXT_MEASUREMENT_SCALE))
            font = ImageFont.truetype(str(font_path), measured_size)
            _left, top, _right, bottom = font.getbbox(text, anchor="ls")
            return (
                ((top + bottom) / 2) / TEXT_MEASUREMENT_SCALE
            ) + TEXT_RENDERING_CENTER_CORRECTION_POINTS
        except Exception:
            pass

    ascent, descent = pdfmetrics.getAscentDescent(font_name, font_size)
    return -((ascent + descent) / 2)


def _render_fast_pdf_text_image(
    text: str,
    font_path: Path,
    font_size: float,
    max_width: float,
    max_height: float,
) -> bytes | None:
    if max_width <= 0 or max_height <= 0 or not text:
        return None

    try:
        from PIL import Image, ImageDraw, ImageFont, features
    except ImportError:
        return None

    if not features.check("raqm"):
        return None

    scale = FAST_PDF_TEXT_IMAGE_SCALE
    image_width = max(1, int(round(max_width * scale)))
    image_height = max(1, int(round(max_height * scale)))
    language = _rtl_text_language(text)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    probe_draw = ImageDraw.Draw(probe)

    fitted_font = None
    fitted_bbox = None
    fitted_size = font_size
    while fitted_size > 1:
        font = _load_pillow_font(ImageFont, font_path, fitted_size * scale)
        bbox = probe_draw.textbbox(
            (0, 0),
            text,
            font=font,
            direction="rtl",
            language=language,
        )
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        if text_width <= image_width and text_height <= image_height:
            fitted_font = font
            fitted_bbox = bbox
            break
        fitted_size -= 1

    if fitted_font is None or fitted_bbox is None:
        font = _load_pillow_font(ImageFont, font_path, scale)
        bbox = probe_draw.textbbox(
            (0, 0),
            text,
            font=font,
            direction="rtl",
            language=language,
        )
        fitted_font = font
        fitted_bbox = bbox

    text_image = Image.new("RGBA", (image_width, image_height), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_image)
    text_width = fitted_bbox[2] - fitted_bbox[0]
    text_height = fitted_bbox[3] - fitted_bbox[1]
    text_x = ((image_width - text_width) / 2) - fitted_bbox[0]
    text_y = ((image_height - text_height) / 2) - fitted_bbox[1]
    text_draw.text(
        (text_x, text_y),
        text,
        font=fitted_font,
        fill=(255, 255, 255, 255),
        direction="rtl",
        language=language,
    )

    output = BytesIO()
    text_image.save(output, format="PNG")
    return output.getvalue()


def _load_pillow_font(ImageFont, font_path: Path, scaled_font_size: float):
    layout_engine = getattr(getattr(ImageFont, "Layout", None), "RAQM", None)
    kwargs = {"layout_engine": layout_engine} if layout_engine is not None else {}
    return ImageFont.truetype(
        str(font_path),
        max(1, int(round(scaled_font_size))),
        **kwargs,
    )


def _fast_pdf_display_text(text: str) -> str:
    if not _contains_rtl_text(text):
        return text

    from arabic_reshaper import reshape
    from bidi.algorithm import get_display

    return get_display(reshape(text))


def _contains_rtl_text(text: str) -> bool:
    return RTL_TEXT_PATTERN.search(text) is not None


def _rtl_text_language(text: str) -> str:
    if PERSIAN_TEXT_PATTERN.search(text):
        return "fa-IR"
    return "ar-SA"


def _fit_text_size(
    text: str,
    font_name: str,
    font_size: float,
    max_width: float,
    pdfmetrics,
) -> float:
    if max_width <= 0 or not text:
        return font_size

    while (
        font_size > MIN_FAST_PDF_FONT_SIZE
        and pdfmetrics.stringWidth(text, font_name, font_size) > max_width
    ):
        font_size -= 1

    width = pdfmetrics.stringWidth(text, font_name, font_size)
    if width > max_width and width > 0:
        return max(1, font_size * (max_width / width))

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
            background_image = _read_background_image(
                archive,
                document_root,
                page_width,
                page_height,
            )
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
            visual_textbox = _detect_background_textbox(
                background_image=background_image,
                page_width=page_width,
                page_height=page_height,
                textbox_x=textbox_x,
                textbox_y=textbox_y,
                textbox_width=textbox_width,
                textbox_height=textbox_height,
            )
            if visual_textbox is not None:
                textbox_x, textbox_y, textbox_width, textbox_height = visual_textbox
            inset_left, inset_top, inset_right, inset_bottom = _read_textbox_insets(text_anchor)
            font_size = _read_placeholder_font_size(text_anchor, placeholder)
    except (KeyError, ValueError, ElementTree.ParseError, zipfile.BadZipFile):
        return None

    if textbox_width <= 0 or textbox_height <= 0:
        return None
    if textbox_width - inset_left - inset_right <= 0:
        return None
    if textbox_height - inset_top - inset_bottom <= 0:
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
        if placeholder in _visible_word_text(anchor):
            return anchor
    return None


def _detect_background_textbox(
    background_image: bytes,
    page_width: float,
    page_height: float,
    textbox_x: float,
    textbox_y: float,
    textbox_width: float,
    textbox_height: float,
) -> tuple[float, float, float, float] | None:
    try:
        from PIL import Image

        with Image.open(BytesIO(background_image)) as image:
            image = image.convert("RGB")
            image_width = image.width
            image_height = image.height
            padding = BACKGROUND_BOX_DETECTION_PADDING_POINTS
            left = _points_to_pixels(max(textbox_x - padding, 0), page_width, image_width)
            top = _points_to_pixels(max(textbox_y - padding, 0), page_height, image_height)
            right = _points_to_pixels(
                min(textbox_x + textbox_width + padding, page_width),
                page_width,
                image_width,
            )
            bottom = _points_to_pixels(
                min(textbox_y + textbox_height + padding, page_height),
                page_height,
                image_height,
            )
            orange_pixels: list[tuple[int, int]] = []

            for y in range(top, bottom):
                for x in range(left, right):
                    if _is_name_box_orange(image.getpixel((x, y))):
                        orange_pixels.append((x, y))
    except Exception:
        return None

    if len(orange_pixels) < 100:
        return None

    min_x = min(x for x, _y in orange_pixels)
    max_x = max(x for x, _y in orange_pixels)
    min_y = min(y for _x, y in orange_pixels)
    max_y = max(y for _x, y in orange_pixels)
    detected_x = _pixels_to_points(min_x, image_width, page_width)
    detected_y = _pixels_to_points(min_y, image_height, page_height)
    detected_width = _pixels_to_points(max_x - min_x + 1, image_width, page_width)
    detected_height = _pixels_to_points(max_y - min_y + 1, image_height, page_height)

    if not (
        textbox_width * 0.7 <= detected_width <= textbox_width * 1.3
        and textbox_height * 0.7 <= detected_height <= textbox_height * 1.3
    ):
        return None

    return detected_x, detected_y, detected_width, detected_height


def _is_name_box_orange(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    return red > 220 and 55 < green < 150 and blue < 70


def _points_to_pixels(points: float, page_points: float, image_pixels: int) -> int:
    return max(0, min(round((points / page_points) * image_pixels), image_pixels))


def _pixels_to_points(pixels: int, image_pixels: int, page_points: float) -> float:
    return (pixels / image_pixels) * page_points


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
    page_width: float,
    page_height: float,
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
                    image = _read_full_page_image(
                        archive,
                        image_path,
                        page_width,
                        page_height,
                    )
                    if image is not None:
                        return image

    media_images = [
        name
        for name in archive.namelist()
        if name.startswith("word/media/") and name.lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    if len(media_images) == 1:
        return _read_full_page_image(archive, media_images[0], page_width, page_height)
    return None


def _read_full_page_image(
    archive: zipfile.ZipFile,
    image_path: str,
    page_width: float,
    page_height: float,
) -> bytes | None:
    image = archive.read(image_path)
    if _image_matches_page(image, page_width, page_height):
        return image
    return None


def _image_matches_page(image: bytes, page_width: float, page_height: float) -> bool:
    dimensions = _image_dimensions(image)
    if dimensions is None:
        return False
    width, height = dimensions
    if min(width, height) < 300 or page_width <= 0 or page_height <= 0:
        return False
    image_ratio = width / height
    page_ratio = page_width / page_height
    return abs(image_ratio - page_ratio) / page_ratio <= 0.05


def _image_dimensions(image: bytes) -> tuple[int, int] | None:
    if image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) >= 24:
        return int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")

    if image.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(image)

    return None


def _jpeg_dimensions(image: bytes) -> tuple[int, int] | None:
    index = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }

    while index < len(image):
        while index < len(image) and image[index] != 0xFF:
            index += 1
        while index < len(image) and image[index] == 0xFF:
            index += 1
        if index >= len(image):
            return None

        marker = image[index]
        index += 1
        if marker == 0xD9 or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(image):
            return None

        segment_length = int.from_bytes(image[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(image):
            return None
        if marker in sof_markers and segment_length >= 7:
            height = int.from_bytes(image[index + 3 : index + 5], "big")
            width = int.from_bytes(image[index + 5 : index + 7], "big")
            return width, height

        index += segment_length

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
        if placeholder not in _visible_word_text(paragraph):
            continue
        size = paragraph.find(".//w:sz", XML_NAMESPACES)
        if size is not None:
            return int(size.attrib[_w_attr("val")]) / 2
    return 36


def _visible_word_text(element: ElementTree.Element) -> str:
    return "".join(text.text or "" for text in element.findall(".//w:t", XML_NAMESPACES))


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
    replaced = False
    rtl_language = _rtl_text_language(name) if _contains_rtl_text(name) else None

    with zipfile.ZipFile(template_path, "r") as source:
        if DOCUMENT_XML not in source.namelist():
            raise CertificateGenerationError(
                f"{template_path} does not contain {DOCUMENT_XML}."
            )

        with zipfile.ZipFile(output_docx_path, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                content = source.read(item.filename)
                if _is_word_text_part(item.filename):
                    document_xml = content.decode("utf-8")
                    if font_family:
                        document_xml = _replace_placeholder_font_style(
                            document_xml,
                            placeholder,
                            font_family,
                            rtl_language=rtl_language,
                        )
                    elif rtl_language:
                        document_xml = _replace_placeholder_text_direction(
                            document_xml,
                            placeholder,
                            rtl_language,
                        )
                    document_xml, part_replaced = _replace_placeholder_text(
                        document_xml,
                        placeholder,
                        name,
                    )
                    content = document_xml.encode("utf-8")
                    replaced = replaced or part_replaced
                target.writestr(item, content)

    if not replaced:
        raise CertificateGenerationError(
            "Placeholder text was not found in the Word document content: "
            f"{placeholder}"
        )


def _is_word_text_part(filename: str) -> bool:
    return WORD_TEXT_PART_PATTERN.match(filename) is not None


def _replace_placeholder_text(
    document_xml: str,
    placeholder: str,
    replacement: str,
) -> tuple[str, bool]:
    replaced = False
    found_paragraph = False

    def replace_paragraph(match: re.Match[str]) -> str:
        nonlocal found_paragraph, replaced
        found_paragraph = True
        paragraph, paragraph_replaced = _replace_text_in_word_text_nodes(
            match.group(0),
            placeholder,
            replacement,
        )
        replaced = replaced or paragraph_replaced
        return paragraph

    updated_xml = WORD_PARAGRAPH_PATTERN.sub(replace_paragraph, document_xml)
    if found_paragraph:
        return updated_xml, replaced

    return _replace_text_in_word_text_nodes(document_xml, placeholder, replacement)


def _replace_text_in_word_text_nodes(
    xml_fragment: str,
    placeholder: str,
    replacement: str,
) -> tuple[str, bool]:
    matches = list(WORD_TEXT_PATTERN.finditer(xml_fragment))
    if not matches:
        return xml_fragment, False

    text_values = [unescape(match.group(2)) for match in matches]
    full_text = "".join(text_values)
    occurrences = _find_text_occurrences(full_text, placeholder)
    if not occurrences:
        return xml_fragment, False

    spans: list[tuple[int, int]] = []
    cursor = 0
    for text in text_values:
        start = cursor
        cursor += len(text)
        spans.append((start, cursor))

    for start, end in reversed(occurrences):
        start_node, start_offset = _text_position_to_node(spans, start)
        end_node, end_offset = _text_position_to_node(spans, end, prefer_previous=True)
        if start_node == end_node:
            text = text_values[start_node]
            text_values[start_node] = text[:start_offset] + replacement + text[end_offset:]
            continue

        text_values[start_node] = text_values[start_node][:start_offset] + replacement
        for node_index in range(start_node + 1, end_node):
            text_values[node_index] = ""
        text_values[end_node] = text_values[end_node][end_offset:]

    parts: list[str] = []
    last_index = 0
    for match, text in zip(matches, text_values):
        parts.append(xml_fragment[last_index : match.start(2)])
        parts.append(escape(text))
        last_index = match.end(2)
    parts.append(xml_fragment[last_index:])

    return "".join(parts), True


def _find_text_occurrences(text: str, needle: str) -> list[tuple[int, int]]:
    occurrences: list[tuple[int, int]] = []
    if not needle:
        return occurrences

    start = 0
    while True:
        index = text.find(needle, start)
        if index == -1:
            return occurrences
        end = index + len(needle)
        occurrences.append((index, end))
        start = end


def _text_position_to_node(
    spans: list[tuple[int, int]],
    position: int,
    prefer_previous: bool = False,
) -> tuple[int, int]:
    for index, (start, end) in enumerate(spans):
        if start <= position < end:
            return index, position - start
        if prefer_previous and start < end and position == end:
            return index, end - start

    if position == 0 and spans:
        return 0, 0
    raise ValueError(f"Text position {position} does not map to a Word text node.")


def _replace_placeholder_font_style(
    document_xml: str,
    placeholder: str,
    font_family: str,
    font_color: str = CERTIFICATE_TEXT_COLOR,
    rtl_language: str | None = None,
) -> str:
    font_attr = escape(font_family, {'"': "&quot;"})
    color_attr = escape(font_color, {'"': "&quot;"})

    def replace_paragraph(match: re.Match[str]) -> str:
        paragraph = match.group(0)
        if not _word_fragment_contains_text(paragraph, placeholder):
            return paragraph
        if rtl_language:
            paragraph = _ensure_paragraph_bidi(paragraph)
        return _replace_run_style_tags(paragraph, font_attr, color_attr, rtl_language)

    return WORD_PARAGRAPH_PATTERN.sub(replace_paragraph, document_xml)


def _replace_placeholder_text_direction(
    document_xml: str,
    placeholder: str,
    rtl_language: str,
) -> str:
    def replace_paragraph(match: re.Match[str]) -> str:
        paragraph = match.group(0)
        if not _word_fragment_contains_text(paragraph, placeholder):
            return paragraph
        paragraph = _ensure_paragraph_bidi(paragraph)
        return _replace_run_style_tags(
            paragraph,
            font_attr=None,
            color_attr=None,
            rtl_language=rtl_language,
        )

    return WORD_PARAGRAPH_PATTERN.sub(replace_paragraph, document_xml)


def _replace_placeholder_font_family(
    document_xml: str,
    placeholder: str,
    font_family: str,
) -> str:
    return _replace_placeholder_font_style(document_xml, placeholder, font_family)


def _word_fragment_contains_text(xml_fragment: str, text: str) -> bool:
    return text in "".join(
        unescape(match.group(2)) for match in WORD_TEXT_PATTERN.finditer(xml_fragment)
    )


def _replace_run_style_tags(
    xml_fragment: str,
    font_attr: str | None,
    color_attr: str | None,
    rtl_language: str | None = None,
) -> str:
    def replace_run(match: re.Match[str]) -> str:
        run = match.group(0)
        if "<w:t" not in run:
            return run
        if font_attr is not None:
            if "<w:rFonts" in run:
                run = _replace_existing_rfonts(run, font_attr)
            else:
                run = _insert_rfonts_tag(run, font_attr)
        if color_attr is not None:
            if "<w:color" in run:
                run = _replace_existing_color(run, color_attr)
            else:
                run = _insert_color_tag(run, color_attr)
        if rtl_language:
            run = _ensure_run_rtl(run, rtl_language)
        return run

    return WORD_RUN_PATTERN.sub(replace_run, xml_fragment)


def _ensure_paragraph_bidi(xml_fragment: str) -> str:
    empty_paragraph_properties = re.search(r"<w:pPr\b([^>]*)/>", xml_fragment)
    if empty_paragraph_properties is not None:
        attributes = empty_paragraph_properties.group(1).rstrip()
        return (
            xml_fragment[: empty_paragraph_properties.start()]
            + f"<w:pPr{attributes}><w:bidi/></w:pPr>"
            + xml_fragment[empty_paragraph_properties.end() :]
        )

    paragraph_properties = re.search(r"<w:pPr\b[^>]*>", xml_fragment)
    if paragraph_properties is not None:
        properties_end = xml_fragment.find("</w:pPr>", paragraph_properties.end())
        if properties_end == -1:
            return xml_fragment
        properties_xml = xml_fragment[paragraph_properties.end() : properties_end]
        if "<w:bidi" in properties_xml:
            return xml_fragment
        return (
            xml_fragment[: paragraph_properties.end()]
            + "<w:bidi/>"
            + xml_fragment[paragraph_properties.end() :]
        )

    paragraph = re.match(r"<w:p\b[^>]*>", xml_fragment)
    if paragraph is None:
        return xml_fragment
    return (
        xml_fragment[: paragraph.end()]
        + "<w:pPr><w:bidi/></w:pPr>"
        + xml_fragment[paragraph.end() :]
    )


def _ensure_run_rtl(xml_fragment: str, rtl_language: str) -> str:
    if "<w:rtl" not in xml_fragment:
        xml_fragment = _insert_run_property_tag(xml_fragment, "<w:rtl/>")
    if "<w:lang" in xml_fragment:
        return _replace_existing_language(xml_fragment, rtl_language)
    return _insert_run_property_tag(xml_fragment, _language_tag(rtl_language))


def _replace_rfonts_tags(xml_fragment: str, font_attr: str) -> str:
    def replace_run(match: re.Match[str]) -> str:
        run = match.group(0)
        if "<w:t" not in run:
            return run
        if "<w:rFonts" in run:
            return _replace_existing_rfonts(run, font_attr)
        return _insert_rfonts_tag(run, font_attr)

    return WORD_RUN_PATTERN.sub(replace_run, xml_fragment)


def _replace_existing_rfonts(xml_fragment: str, font_attr: str) -> str:
    def replace_rfonts(match: re.Match[str]) -> str:
        tag = match.group(0)
        for attr_name in ("ascii", "hAnsi", "cs", "eastAsia"):
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


def _replace_existing_color(xml_fragment: str, color_attr: str) -> str:
    def replace_color(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "w:val=" in tag:
            return re.sub(
                r'(w:val=")[^"]*(")',
                lambda attr_match: f"{attr_match.group(1)}{color_attr}{attr_match.group(2)}",
                tag,
                count=1,
            )
        insert_at = -2 if tag.endswith("/>") else -1
        return f'{tag[:insert_at]} w:val="{color_attr}"{tag[insert_at:]}'

    return re.sub(r"<w:color\b[^>]*/?>", replace_color, xml_fragment)


def _replace_existing_language(xml_fragment: str, rtl_language: str) -> str:
    language_attr = escape(rtl_language, {'"': "&quot;"})

    def replace_language(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "w:bidi=" in tag:
            return re.sub(
                r'(w:bidi=")[^"]*(")',
                lambda attr_match: f"{attr_match.group(1)}{language_attr}{attr_match.group(2)}",
                tag,
                count=1,
            )
        insert_at = -2 if tag.endswith("/>") else -1
        return f'{tag[:insert_at]} w:bidi="{language_attr}"{tag[insert_at:]}'

    return re.sub(r"<w:lang\b[^>]*/?>", replace_language, xml_fragment)


def _insert_rfonts_tag(xml_fragment: str, font_attr: str) -> str:
    return _insert_run_property_tag(xml_fragment, _rfonts_tag(font_attr))


def _insert_color_tag(xml_fragment: str, color_attr: str) -> str:
    return _insert_run_property_tag(xml_fragment, _color_tag(color_attr))


def _insert_run_property_tag(xml_fragment: str, property_tag: str) -> str:
    empty_run_properties = re.search(r"<w:rPr\b([^>]*)/>", xml_fragment)
    if empty_run_properties is not None:
        attributes = empty_run_properties.group(1).rstrip()
        return (
            xml_fragment[: empty_run_properties.start()]
            + f"<w:rPr{attributes}>{property_tag}</w:rPr>"
            + xml_fragment[empty_run_properties.end() :]
        )

    run_properties = re.search(r"<w:rPr\b[^>]*>", xml_fragment)
    if run_properties is not None:
        return (
            xml_fragment[: run_properties.end()]
            + property_tag
            + xml_fragment[run_properties.end() :]
        )

    run = re.match(r"<w:r\b[^>]*>", xml_fragment)
    if run is None:
        return xml_fragment
    return (
        xml_fragment[: run.end()]
        + f"<w:rPr>{property_tag}</w:rPr>"
        + xml_fragment[run.end() :]
    )


def _rfonts_tag(font_attr: str) -> str:
    return (
        f'<w:rFonts w:ascii="{font_attr}" w:hAnsi="{font_attr}" '
        f'w:cs="{font_attr}" w:eastAsia="{font_attr}"/>'
    )


def _color_tag(color_attr: str) -> str:
    return f'<w:color w:val="{color_attr}"/>'


def _language_tag(rtl_language: str) -> str:
    language_attr = escape(rtl_language, {'"': "&quot;"})
    return f'<w:lang w:bidi="{language_attr}"/>'


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
