"""多人共享记账系统（轻量级 Windows 桌面版）。

本包按分层结构组织：

* :mod:`ledgershare.domain` —— 与存储无关的领域规则（权限、状态机、校验）；
* :mod:`ledgershare.data`   —— SQLite 存储与仓储；
* :mod:`ledgershare.services` —— 应用服务，实现实验一需求基线；
* :mod:`ledgershare.ui`     —— PySide6 图形界面。
"""

__version__ = "1.0.0"
