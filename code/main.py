# pylint: disable=wrong-import-position
"""程序启动脚本：``python main.py`` 或打包后的 exe 都从这里进入。

支持一个打包自检参数，用于验证 exe 的运行时依赖是否齐全：

    LedgerShare.exe --selftest [日志文件路径]
"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许直接以脚本方式运行（不安装为包）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ledgershare.selftest import run as run_selftest  # noqa: E402 - 需在 sys.path 设置之后导入
from ledgershare.ui.app import main  # noqa: E402


def _main() -> int:
    """根据命令行参数决定进入界面还是运行自检。"""
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        # 允许日志路径带空格：把剩余参数重新拼起来
        rest = " ".join(sys.argv[index + 1 :]).strip()
        return run_selftest(Path(rest) if rest else None)
    return main()


if __name__ == "__main__":
    raise SystemExit(_main())
