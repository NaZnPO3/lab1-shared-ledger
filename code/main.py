"""程序启动脚本：``python main.py`` 或打包后的 exe 都从这里进入。"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许直接以脚本方式运行（不安装为包）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ledgershare.ui.app import main  # noqa: E402 - 需在 sys.path 设置之后导入

if __name__ == "__main__":
    raise SystemExit(main())
