# LedgerShare · 轻量级多人共享记账（实验三实现）

实验一需求基线（`requirements.md`，REQ-001 ~ REQ-026）的 Windows 桌面实现。
技术栈：**Python 3.13 + PySide6 + SQLite**，单机多账号，一个数据库文件即可共享账本。

## 快速开始

```powershell
cd code
python -m pip install -r requirements.txt   # 只有 PySide6 一个第三方依赖
python main.py
```

首次运行会在 `%LOCALAPPDATA%\LedgerShare\ledger.db` 建库；也可以用环境变量
`LEDGERSHARE_DB` 指定数据库文件位置。

验证与质量检查：

```powershell
python -m pytest -q                      # 82 个测试
python -m pylint ledgershare tests tools # 代码风格检查，当前 10.00/10
python tools/capture_ui.py               # 生成界面截图到 ../docs/screenshots
```

打包成单文件 exe：

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name LedgerShare --paths . main.py
```

## 目录结构

```
code/
├── main.py                     启动脚本
├── ledgershare/
│   ├── config.py               金额上限、默认分类、数据目录
│   ├── enums.py                角色、状态、权限项、日志动作
│   ├── errors.py               领域异常
│   ├── models.py               实体（与实验二类图对应）
│   ├── money.py                金额换算（统一按"分"存整数）
│   ├── timeutil.py             时间格式化
│   ├── domain/                 纯规则：权限矩阵、状态机、输入校验
│   ├── data/                   SQLite 建表、连接与事务、仓储
│   ├── services/               应用服务：认证/账本/记录/审核/结算/统计/日志/幂等
│   └── ui/                     PySide6 界面
├── tests/                      pytest 测试
└── tools/capture_ui.py         无界面环境下的截图脚本
```

分层依赖方向：`ui → services → domain / data → models`，`domain` 不依赖数据库和界面，
因此权限与状态机可以脱离存储单独测试。

## 实验二类图到代码的映射

| UML 类 | 代码位置 |
|---|---|
| `User` | `models.User` + `services/auth_service.py` |
| `Ledger` | `models.Ledger` + `services/ledger_service.py` |
| `Member`（角色挂在成员上） | `models.Member` + `domain/permissions.py` |
| `Category` | `models.Category` + `data/repositories.CategoryRepository` |
| `TransactionRecord` | `models.TransactionRecord` + `services/record_service.py`、`review_service.py` |
| `SettlementPeriod` | `models.SettlementPeriod` + `services/settlement_service.py` |
| `OperationLog` | `models.OperationLogEntry` + `services/log_service.py` |
| `RecordStatus` 枚举 | `enums.RecordStatus` + `domain/state_machine.py` |

实验二组件图里的「API 网关 + 六个微服务 + 双数据库」在桌面单机场景下属于过度设计，
实现时收敛为「一个进程内分层 + 一个 SQLite 文件」，但保留了实验二强调的两条原则：
权限集中校验（`BaseService.authorize`）、日志只追加（`operation_logs` 无 UPDATE/DELETE）。

## 需求到实现与测试的对照

| 需求 | 实现要点 | 测试 |
|---|---|---|
| REQ-004 成员退出 | 当前周期有未结记录时拒绝退出 | `test_ledger.py` |
| REQ-005 新增记录 | 必填校验、状态置“待审核” | `test_record.py` |
| REQ-006 撤回 | 仅原记录人、仅待审核 | `test_record.py` |
| REQ-007 修改重提 | 仅已驳回、状态回待审核、版本号递增 | `test_record.py` |
| REQ-008 审核 | 管理员通过/驳回，乐观锁防重复审核 | `test_review.py` |
| REQ-009 作废 | 仅已审核记录可作废，记录保留 | `test_review.py` |
| REQ-010 更正 | 更正是指向原记录的新记录，通过后原作废 | `test_correction.py` |
| REQ-015 金额校验 | 拒绝 0、负数、超上限；上限可配置 | `test_money_validation.py` |
| REQ-016 幂等 | 幂等键 + 请求摘要，重复提交返回首次结果 | `test_idempotency.py` |
| REQ-017 并发冲突 | 状态机 + `version` 乐观锁 | `test_idempotency.py`（多线程） |
| REQ-018 操作日志 | 审核/驳回/作废/更正/越权/结算失败全部留痕 | `test_logs.py` |
| REQ-019 退出保留记录 | 成员退出不改动历史记录 | `test_ledger.py` |
| REQ-020 越权不改数据 | 集中权限校验，拒绝且写日志 | `test_permissions.py`、`test_logs.py` |
| REQ-021 结算一致性 | 单事务 + 失败回滚 + 失败日志 | `test_settlement.py` |
| REQ-025 周期锁定 | 已结算周期记录只读 | `test_settlement.py` |

范围决策：状态为「待确认」且规则未定的 REQ-012（预算）、REQ-026（自动周期结算）未实现；
REQ-001/002/003/011/013/014 作为已确认需求的必要骨架做了最小实现。

## 结算规则

需求基线的分摊公式仍标为“待确认”，实现采用并在界面与README中明示的确定规则：

1. 结算范围：当前进行中周期内、状态为“已审核”的记录；
2. 支出由全体在册成员平均分摊，除不尽的“分”按成员 ID 顺序补 1 分，保证分摊合计等于支出合计；
3. 收入归记录人个人，不参与分摊；
4. `应收付 = 本人垫付支出 - 本人应分摊支出`，全体相加为 0；
5. 结算后当前周期锁定，并自动开启下一周期，账本继续可用。

结算前若仍有“待审核”记录，结算会被拒绝并写入 `settle_failed` 日志，避免把未审核数据固化。

## 并发与一致性

* SQLite 使用 WAL + `BEGIN IMMEDIATE`，写事务串行化；
* 记录更新走 `UPDATE ... WHERE status = ? AND version = ?`，受影响行数为 0 即视为状态冲突；
* 幂等键与业务记录在同一事务内写入，重复提交不会产生第二条记录或第二条日志。

## 已知取舍

* 单机多账号：需求基线未要求联网，跨机器共享只需把数据库换成共享路径或换 SQLite 为网络库；
* 密码用 PBKDF2-HMAC-SHA256 + 随机盐保存在本地库，不适用于真正的多用户服务器场景；
* 界面未做自定义分类管理，账本创建时自动生成常用分类。
