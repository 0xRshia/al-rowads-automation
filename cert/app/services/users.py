from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import config


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


@dataclass(frozen=True)
class User:
    username: str
    password_hash: str
    is_admin: bool = False


class UserStore:
    def __init__(self, path: Path = config.user_store_path):
        self.path = path
        self.ensure_initialized()

    def ensure_initialized(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            return
        admin = User(
            username=DEFAULT_ADMIN_USERNAME,
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            is_admin=True,
        )
        self.save_users({admin.username: admin})

    def load_users(self) -> dict[str, User]:
        self.ensure_initialized()
        raw_users = json.loads(self.path.read_text(encoding="utf-8"))
        return {username: User(**data) for username, data in raw_users.items()}

    def save_users(self, users: dict[str, User]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {username: asdict(user) for username, user in users.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.load_users().get(username)
        if not user or not verify_password(password, user.password_hash):
            return None
        return user

    def get(self, username: str) -> User | None:
        return self.load_users().get(username)


def hash_password(password: str, iterations: int = 260_000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError):
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)
