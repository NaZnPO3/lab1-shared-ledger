# lab1-shared-ledger

多人共享记账系统 —— 《软件工程》课程实验一至实验三的完整成果。

| 实验 | 内容 | 产物 | 标签 |
|---|---|---|---|
| 实验一 | 需求分析 | `requirements.md`（REQ-001 ~ REQ-026） | `lab1-final` |
| 实验二 | 软件设计与建模 | `uml/`、`ui/`、`UI界面/` | `lab2-final` |
| 实验三 | 软件实现与构建 | `code/`、`docs/screenshots/` | `lab3-final` |

## 目录结构

```
lab1-shared-ledger/
├── requirements.md            实验一需求基线（REQ-001 ~ REQ-026）
├── chat.txt                   需求访谈记录素材
├── uml/                       实验二 UML：类图 / 组件图 / 用例图 / 时序图（.puml + .png）
│                              └ 含 *-实现修订：按实验三实现回写的类图与组件图
├── ui/                        实验二界面原型（HTML + CSS）
├── UI界面/                    实验二界面草图（JPEG）
├── report/                    实验一、实验二报告
├── code/                      实验三源代码（Python + PySide6 + SQLite）
│   ├── ledgershare/           domain / data / services / ui 四层
│   ├── tests/                 pytest 测试
│   ├── tools/capture_ui.py    界面截图脚本
│   ├── build.py               单文件 exe 打包脚本
│   └── README.md              实现说明、需求覆盖表、结算规则
└── docs/screenshots/          实验三运行截图
```

## 实验三：运行与验证

```powershell
cd code
python -m pip install -r requirements.txt
python main.py                        # 启动桌面程序
python -m pytest                      # 82 个测试全部通过
python -m pylint ledgershare tests tools   # 代码风格检查 10.00/10
python build.py                       # 打包 dist/LedgerShare.exe
```

技术栈：Python 3.13 + PySide6 + SQLite，单机多账号，一个数据库文件即可共享账本。
数据库默认位于 `%LOCALAPPDATA%\LedgerShare\ledger.db`，可用环境变量 `LEDGERSHARE_DB` 指定。

## 实验二设计取舍

| 决策 | 理由 |
|---|---|
| 角色挂在 `Member` 而非 `User` | 同一用户在不同账本中角色不同 |
| 更正是一条指向原记录的新记录 | 已审核记录不可直接修改（REQ-010） |
| 新增 `SettlementPeriod` | 结算后锁定的对象落点（REQ-025） |
| 日志只追加 | 审计信息不能随业务回滚消失（REQ-018） |

## 实验三与实验二设计的差异

实验二组件图设计了「API 网关 + 六个微服务 + 业务库/日志库分离」。
实验三按“轻量级 Windows 桌面”的目标收敛为单进程分层架构，但保留了设计阶段的两条核心原则：

* 权限集中校验（`code/ledgershare/services/base.py` 的 `authorize`），对应 REQ-020；
* 越权日志写在独立事务中，业务回滚不会带走日志，对应 REQ-018。

需求覆盖、结算分摊规则、并发与幂等实现细节见 [`code/README.md`](code/README.md)。

### 设计回写

实验三实现完成后，按实际情况回写了两张图（与实验二原图并存，便于对比）：

| 文件 | 与实验二原图的差异 |
|---|---|
| `uml/UML类图-实现修订.puml` | 字段名与代码实体一致；`TransactionRecord` 增加 `periodId`（REQ-025）、`correctsRecordId`（REQ-010）、`version`（REQ-017）；新增 `SettlementLine` 承载每人的垫付/应分摊/应收付；`Budget` 标注为未实现 |
| `uml/UML组件图-实现修订.puml` | 取消 API 网关与独立服务进程，收敛为「表现层 → 应用服务层 → 领域层 / 数据访问层 → SQLite」四层；保留权限集中校验、幂等执行器与日志只追加 |

重新渲染命令（PlantUML 放在仓库外的 `实验工具/plantuml.jar`）：

```powershell
java -jar plantuml.jar -charset UTF-8 -tpng uml/*-实现修订.puml
```
