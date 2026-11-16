"""规格（DesignSpecContent）确定性校验。

结构、必填与需求 ID 唯一性已由契约模型（`flowstudio_contracts.spec`）在解析时强制，
非法输入在进入本函数前就是 422；此处只给出可复核的通过报告与输入散列，不重复实现
同一套规则，也不宣称能识别语义矛盾（那属于 PM 的 blocking_questions 与人工评审）。
"""

from __future__ import annotations

from flowstudio_contracts import (
    DesignSpecContent,
    RULES_VERSION,
    ValidationReport,
    content_hash,
)
from flowstudio_contracts.validation import Coverage


def validate_spec(content: DesignSpecContent) -> ValidationReport:
    return ValidationReport(
        valid=True,
        errors=[],
        warnings=[],
        coverage=Coverage(covered_ids=[], uncovered_ids=[]),
        rules_version=RULES_VERSION,
        input_hash=content_hash(content),
    )
