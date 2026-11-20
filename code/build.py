"""打包脚本：把程序打成单文件 exe。

直接调用 ``pyinstaller main.py`` 在 conda 环境下会遇到
``ImportError: DLL load failed while importing _sqlite3``——conda 把
``sqlite3.dll`` 放在 ``Library/bin`` 而不是 Python 的 DLLs 目录，
PyInstaller 不会自动收集。本脚本按当前 Python 解释器位置找到该 DLL 并显式加入，
换一台机器（标准 CPython 安装）时自动跳过这一步。

用法::

    python build.py            # 单文件、无控制台窗口
    python build.py --console  # 带控制台，便于排查启动问题
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
APP_NAME = "LedgerShare"


def find_conda_sqlite_dll() -> Path | None:
    """在 conda 环境中定位 ``sqlite3.dll``，标准安装返回 ``None``。"""
    candidates = [
        Path(sys.base_prefix) / "Library" / "bin" / "sqlite3.dll",
        Path(sys.base_prefix) / "DLLs" / "sqlite3.dll",
        Path(sys.base_prefix).parent / "Library" / "bin" / "sqlite3.dll",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_openssl_dlls() -> list[Path]:
    """定位 OpenSSL 运行库。

    ``_hashlib`` 依赖 ``libcrypto``，缺了它会退回纯 Python 的 ``hashlib``，
    而纯 Python 版没有 ``pbkdf2_hmac``，导致注册/登录直接抛
    ``AttributeError: module 'hashlib' has no attribute 'pbkdf2_hmac'``。
    """
    roots = [
        Path(sys.base_prefix) / "Library" / "bin",
        Path(sys.base_prefix) / "DLLs",
        Path(sys.base_prefix).parent / "Library" / "bin",
    ]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in ("libcrypto-3-x64.dll", "libssl-3-x64.dll", "libcrypto*.dll", "libssl*.dll"):
            for candidate in sorted(root.glob(pattern)):
                if candidate not in found:
                    found.append(candidate)
    return found


def main(argv: list[str]) -> int:
    """执行打包。"""
    console = "--console" in argv
    arguments = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console" if console else "--windowed",
        "--name",
        f"{APP_NAME}Dbg" if console else APP_NAME,
        "--paths",
        str(CODE_DIR),
    ]

    dll = find_conda_sqlite_dll()
    if dll is not None:
        print(f"附加 sqlite3.dll: {dll}")
        arguments += ["--add-binary", f"{dll};."]

    for openssl_dll in find_openssl_dlls():
        print(f"附加 OpenSSL 运行库: {openssl_dll.name}")
        arguments += ["--add-binary", f"{openssl_dll};."]

    arguments.append("main.py")
    print("执行：", " ".join(arguments))
    return subprocess.call(arguments, cwd=str(CODE_DIR))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
