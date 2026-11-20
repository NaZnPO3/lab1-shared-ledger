"""认证服务：注册与登录。

密码使用 PBKDF2-HMAC-SHA256 加盐散列保存，数据库里不出现明文。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from ..config import PASSWORD_ITERATIONS
from ..domain.validation import (
    validate_display_name,
    validate_password,
    validate_username,
)
from ..errors import AuthError, DuplicateError
from ..models import User
from ..timeutil import now
from .base import BaseService, new_id


def hash_password(password: str, salt: str) -> str:
    """计算密码散列值。"""
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_ITERATIONS
    )
    return digest.hex()


class AuthService(BaseService):
    """用户注册与登录。"""

    def register(
        self, username: str, password: str, display_name: str = ""
    ) -> User:
        """注册新用户。

        Args:
            username: 账号，长度 3~20。
            password: 明文密码，至少 6 位。
            display_name: 昵称，可为空，默认使用账号。

        Returns:
            新建的用户。

        Raises:
            ValidationError: 输入不合法。
            DuplicateError: 账号已存在。
        """
        name = validate_username(username)
        safe_password = validate_password(password)
        nickname = validate_display_name(display_name) or name

        salt = secrets.token_hex(16)
        password_hash = hash_password(safe_password, salt)
        user_id = new_id()

        with self.db.transaction() as conn:
            repository = self._users(conn)
            if repository.exists(name):
                raise DuplicateError("该账号已被注册，请换一个")
            repository.insert(
                user_id=user_id,
                username=name,
                display_name=nickname,
                password_hash=password_hash,
                salt=salt,
                created_at=now(),
            )
            user = repository.by_id(user_id)
        if user is None:  # pragma: no cover - 插入成功后不可能为 None
            raise AuthError("注册失败，请重试")
        return user

    def login(self, username: str, password: str) -> User:
        """校验账号密码并返回用户。

        Raises:
            AuthError: 账号不存在或密码错误。
        """
        name = (username or "").strip()
        with self.db.reading() as conn:
            row = self._users(conn).by_username(name)
            if row is None:
                raise AuthError("账号或密码错误")
            expected = hash_password(password or "", row["salt"])
            if not hmac.compare_digest(expected, row["password_hash"]):
                raise AuthError("账号或密码错误")
            return User.from_row(row)

    def get_user(self, user_id: str) -> User | None:
        """按 ID 读取用户。"""
        with self.db.reading() as conn:
            return self._users(conn).by_id(user_id)
