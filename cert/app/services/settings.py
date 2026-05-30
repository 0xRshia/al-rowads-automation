from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
import re

from app.config import config


@dataclass
class CertificateSettings:
    template_path: str
    font_path: str
    placeholder: str
    template_filename: str | None = None
    font_filename: str | None = None

    @property
    def template(self) -> Path:
        return Path(self.template_path)

    @property
    def font(self) -> Path:
        return Path(self.font_path)

    @property
    def current_template_name(self) -> str:
        return self.template_filename or self.template.name

    @property
    def current_font_name(self) -> str:
        return self.font_filename or self.font.name


class SettingsStore:
    def __init__(self, path: Path = config.settings_path):
        self.path = path
        self.template_dir = path.parent / "templates"
        self.font_dir = path.parent / "fonts"
        self.ensure_initialized()

    def ensure_initialized(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.font_dir.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            return

        template_path = self.template_dir / "certificate.docx"
        font_path = self.font_dir / "certificate-font.ttf"
        shutil.copy2(config.default_template_path, template_path)
        shutil.copy2(config.default_font_path, font_path)
        self.save(
            CertificateSettings(
                template_path=str(template_path),
                font_path=str(font_path),
                placeholder=config.default_placeholder,
                template_filename=config.default_template_path.name,
                font_filename=config.default_font_path.name,
            )
        )

    def load(self) -> CertificateSettings:
        self.ensure_initialized()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("template_filename", Path(data["template_path"]).name)
        data.setdefault("font_filename", Path(data["font_path"]).name)
        return CertificateSettings(**data)

    def save(self, settings: CertificateSettings) -> CertificateSettings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return settings

    def update(
        self,
        placeholder: str,
        template_upload: bytes | None = None,
        template_filename: str | None = None,
        font_upload: bytes | None = None,
        font_filename: str | None = None,
    ) -> CertificateSettings:
        current = self.load()
        template_path = current.template
        font_path = current.font
        template_display_name = current.current_template_name
        font_display_name = current.current_font_name

        if template_upload:
            if not (template_filename or "").lower().endswith(".docx"):
                raise ValueError("Template upload must be a .docx file.")
            template_display_name = _safe_display_filename(template_filename or "certificate.docx")
            template_path = self.template_dir / template_display_name
            template_path.write_bytes(template_upload)

        if font_upload:
            if not (font_filename or "").lower().endswith((".ttf", ".otf")):
                raise ValueError("Font upload must be a .ttf or .otf file.")
            font_display_name = _safe_display_filename(font_filename or "certificate-font.ttf")
            font_path = self.font_dir / font_display_name
            font_path.write_bytes(font_upload)

        placeholder = placeholder.strip()
        if not placeholder:
            raise ValueError("Placeholder cannot be empty.")

        return self.save(
            CertificateSettings(
                template_path=str(template_path),
                font_path=str(font_path),
                placeholder=placeholder,
                template_filename=template_display_name,
                font_filename=font_display_name,
            )
        )


def _safe_display_filename(filename: str) -> str:
    safe_name = Path(filename).name.strip()
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", safe_name)
    safe_name = safe_name.strip(" .")
    return safe_name or "certificate-file"
