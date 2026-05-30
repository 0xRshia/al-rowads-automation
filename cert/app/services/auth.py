from __future__ import annotations

import base64
import hmac
import os
from hashlib import sha256
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from app.config import config
from app.services.users import User, UserStore


def get_session_secret(path: Path = config.session_secret_path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(os.urandom(32))
    return path.read_bytes()


def create_session_token(username: str) -> str:
    username_bytes = username.encode("utf-8")
    signature = hmac.new(get_session_secret(), username_bytes, sha256).digest()
    return "{}.{}".format(
        base64.urlsafe_b64encode(username_bytes).decode("ascii"),
        base64.urlsafe_b64encode(signature).decode("ascii"),
    )


def verify_session_token(token: str) -> str | None:
    try:
        username_part, signature_part = token.split(".", 1)
        username_bytes = base64.urlsafe_b64decode(username_part.encode("ascii"))
        signature = base64.urlsafe_b64decode(signature_part.encode("ascii"))
    except (ValueError, TypeError):
        return None

    expected = hmac.new(get_session_secret(), username_bytes, sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    return username_bytes.decode("utf-8")


def current_user(request: Request) -> User:
    token = request.cookies.get(config.session_cookie_name)
    username = verify_session_token(token or "")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = UserStore().get(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user
