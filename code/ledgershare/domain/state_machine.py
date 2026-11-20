"""收支记录状态机（REQ-005 ~ REQ-010、REQ-025）。

状态迁移只允许下列六种，其余组合一律视为"状态已变化"的冲突，
保证并发审核时不会出现两条记录同时成功或状态回退。
"""

from __future__ import annotations

from ..enums import RecordStatus
from ..errors import StateConflict

#: 允许的状态迁移表：当前状态 -> 可迁移到的目标状态。
ALLOWED_TRANSITIONS: dict[RecordStatus, frozenset[RecordStatus]] = {
    RecordStatus.PENDING: frozenset(
        {
            RecordStatus.APPROVED,   # REQ-008 审核通过
            RecordStatus.REJECTED,   # REQ-008 审核驳回
            RecordStatus.WITHDRAWN,  # REQ-006 原记录人撤回
        }
    ),
    RecordStatus.REJECTED: frozenset(
        {
            RecordStatus.PENDING,  # REQ-007 修改后重新提交
        }
    ),
    RecordStatus.APPROVED: frozenset(
        {
            RecordStatus.VOIDED,  # REQ-009 作废 / REQ-010 更正通过后作废原记录
        }
    ),
    RecordStatus.WITHDRAWN: frozenset(),
    RecordStatus.VOIDED: frozenset(),
}

#: 迁移动作的中文描述，用于错误提示。
TRANSITION_LABELS: dict[tuple[RecordStatus, RecordStatus], str] = {
    (RecordStatus.PENDING, RecordStatus.APPROVED): "审核通过",
    (RecordStatus.PENDING, RecordStatus.REJECTED): "审核驳回",
    (RecordStatus.PENDING, RecordStatus.WITHDRAWN): "撤回",
    (RecordStatus.REJECTED, RecordStatus.PENDING): "修改后重新提交",
    (RecordStatus.APPROVED, RecordStatus.VOIDED): "作废",
}


def can_transition(current: RecordStatus, target: RecordStatus) -> bool:
    """判断状态迁移是否合法。"""
    return target in ALLOWED_TRANSITIONS[current]


def ensure_transition(current: RecordStatus, target: RecordStatus) -> None:
    """断言状态迁移合法。

    Raises:
        StateConflict: 当前状态不允许迁移到目标状态时抛出（REQ-017）。
    """
    if not can_transition(current, target):
        action = TRANSITION_LABELS.get((current, target), "变更状态")
        raise StateConflict(
            f"记录当前状态为“{current.label}”，无法{action}，请刷新后重试"
        )


def is_terminal(status: RecordStatus) -> bool:
    """判断状态是否为终态（不再接受任何变更）。"""
    return not ALLOWED_TRANSITIONS[status]


def allowed_next_states(status: RecordStatus) -> tuple[RecordStatus, ...]:
    """返回当前状态允许迁移到的目标状态，供界面决定按钮是否可点。"""
    return tuple(ALLOWED_TRANSITIONS[status])
