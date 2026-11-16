"""PM 离线测试路径和共享契约样例。"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path[:0] = [str(BACKEND), str(ROOT / "tech")]

from flowstudio_contracts import (  # noqa: E402
    DesignSpecContent,
    PlanningConfig,
    SpecRevision,
    content_hash,
)


def example(name):
    return (ROOT / "tech" / "artifacts" / "examples" / f"{name}.json").read_text(encoding="utf-8")


def spec_revision(**changes):
    spec = DesignSpecContent.model_validate({**json.loads(example("design-spec")), **changes})
    return SpecRevision(
        id="11111111-1111-4111-8111-111111111111",
        spec_id="22222222-2222-4222-8222-222222222222",
        revision=1,
        content=spec,
        hash=content_hash(spec),
        created_at="2026-11-16T08:00:00Z",
    )


def config(**changes):
    return PlanningConfig.model_validate(
        {
            "model": "test-model",
            "granularity": "standard",
            "planning_constraints": [],
            **changes,
        },
    )
