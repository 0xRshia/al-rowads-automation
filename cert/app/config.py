from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
JOB_DIR = DATA_DIR / "jobs"
USER_STORE_PATH = DATA_DIR / "users.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
SESSION_SECRET_PATH = DATA_DIR / "session.secret"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "Certificate.docx"
DEFAULT_FONT_PATH = PROJECT_ROOT / "AbarHigh-SemiBold.ttf"
DEFAULT_PLACEHOLDER = "دکتور احمد الکاتب"
SESSION_COOKIE_NAME = "cert_session"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class AppConfig:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    job_dir: Path = JOB_DIR
    user_store_path: Path = USER_STORE_PATH
    settings_path: Path = SETTINGS_PATH
    session_secret_path: Path = SESSION_SECRET_PATH
    default_template_path: Path = DEFAULT_TEMPLATE_PATH
    default_font_path: Path = DEFAULT_FONT_PATH
    default_placeholder: str = DEFAULT_PLACEHOLDER
    session_cookie_name: str = SESSION_COOKIE_NAME
    max_upload_bytes: int = MAX_UPLOAD_BYTES


config = AppConfig()
