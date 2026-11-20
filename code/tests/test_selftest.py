"""打包自检入口的测试：确保自检能跑通，并在异常时写出可读的日志。"""

from __future__ import annotations

from pathlib import Path

from ledgershare.selftest import run
from ledgershare.ui.helpers import error_log_path, report_unexpected


def test_selftest_returns_zero_and_reports_steps(tmp_path: Path) -> None:
    """自检应完整跑通注册、登录、记账、审核、结算。"""
    log = tmp_path / "selftest.log"

    assert run(log) == 0

    text = log.read_text(encoding="utf-8")
    assert "[ok] 注册用户 selftest_user" in text
    assert "[ok] 登录成功" in text
    assert "[ok] 结算完成" in text
    assert "[failed]" not in text


def test_report_unexpected_writes_traceback(tmp_path: Path, monkeypatch) -> None:
    """未预期异常必须落盘，否则窗口模式下无从排查。"""
    monkeypatch.setenv("LEDGERSHARE_DB", str(tmp_path / "unused.db"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    exc = RuntimeError("打包缺库")
    path = report_unexpected(exc)

    assert path == error_log_path()
    content = path.read_text(encoding="utf-8")
    assert "RuntimeError" in content
    assert "打包缺库" in content
