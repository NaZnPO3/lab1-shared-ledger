"""认证服务测试：注册、登录与重复注册。"""

from __future__ import annotations

import pytest

from ledgershare.errors import AuthError, DuplicateError, ValidationError
from ledgershare.services.auth_service import hash_password


def test_register_and_login(app) -> None:
    """注册后可以用同一组账号密码登录。"""
    user = app.auth.register("alice", "secret123", "爱丽丝")
    assert user.display_name == "爱丽丝"
    logged = app.auth.login("alice", "secret123")
    assert logged.user_id == user.user_id


def test_login_uses_display_name_default(app) -> None:
    """昵称留空时默认使用账号。"""
    user = app.auth.register("bob", "secret123")
    assert user.display_name == "bob"


def test_duplicate_username_rejected(app) -> None:
    """同一账号不能注册两次。"""
    app.auth.register("carol", "secret123")
    with pytest.raises(DuplicateError):
        app.auth.register("carol", "secret456")


def test_wrong_password_rejected(app) -> None:
    """密码错误时给出统一提示，不暴露账号是否存在。"""
    app.auth.register("dave", "secret123")
    with pytest.raises(AuthError):
        app.auth.login("dave", "wrong-pass")
    with pytest.raises(AuthError):
        app.auth.login("nobody", "secret123")


def test_password_is_salted_and_hashed(app) -> None:
    """数据库里不保存明文密码，且使用盐值散列。"""
    app.auth.register("erin", "secret123")
    row = app.db.fetch_one("SELECT password_hash, salt FROM users WHERE username = ?", ("erin",))
    assert row is not None
    assert row["password_hash"] != "secret123"
    assert len(row["salt"]) == 32
    assert row["password_hash"] == hash_password("secret123", row["salt"])


def test_register_validation(app) -> None:
    """账号与密码长度不合规时注册失败。"""
    with pytest.raises(ValidationError):
        app.auth.register("x", "secret123")
    with pytest.raises(ValidationError):
        app.auth.register("valid_name", "123")
