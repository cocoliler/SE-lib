"""契约漂移检查：把 FastAPI 实际注册的操作与 `flowstudio_contracts.api.OPERATIONS` 比对。

OpenAPI 的唯一事实源是 T01 的操作表（tech/artifacts/openapi.json 由它生成），
本脚本不导出自己的 openapi.json，只报告差异并以非零码退出：

    python backend/tools/export_openapi.py

比对内容：
- 方法 + 路径集合是否一一对应（缺路由 / 私加路由都算漂移）；
- 每个操作声明的成功状态码是否存在；
- 成功响应体是否引用契约声明的模型名。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for path in (str(ROOT / "backend"), str(ROOT / "tech")):
    if path not in sys.path:
        sys.path.insert(0, path)

from flowstudio_contracts import API_PREFIX  # noqa: E402
from flowstudio_contracts.api import OPERATIONS, Operation, operation_path  # noqa: E402


def _iter_operations(schema: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in schema.get("paths", {}).items():
        for method, body in item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                found[(method.upper(), path)] = body
    return found


def _response_model_name(operation: Operation) -> str | None:
    model = operation.response_model
    return model.__name__ if model is not None else None


def _ref_name(payload: dict[str, Any]) -> str | None:
    schema = payload.get("content", {}).get("application/json", {}).get("schema", {})
    ref = schema.get("$ref", "")
    return ref.rsplit("/", 1)[-1] if ref else None


def collect_drift(schema: dict[str, Any]) -> list[str]:
    actual = _iter_operations(schema)
    expected = {(operation.method.upper(), operation_path(operation)): operation
                for operation in OPERATIONS}
    problems: list[str] = []

    for key in sorted(set(expected) - set(actual)):
        problems.append(f"缺少路由：{key[0]} {key[1]}")
    for key in sorted(set(actual) - set(expected)):
        problems.append(f"契约外路由：{key[0]} {key[1]}")

    for key, operation in expected.items():
        if key not in actual:
            continue
        responses = actual[key].get("responses", {})
        status = str(operation.success_status)
        if status not in responses:
            problems.append(f"成功状态码漂移：{key[0]} {key[1]} 期望 {status}")
            continue
        expected_name = _response_model_name(operation)
        actual_name = _ref_name(responses[status])
        if expected_name and actual_name and expected_name != actual_name:
            problems.append(
                f"响应模型漂移：{key[0]} {key[1]} 期望 {expected_name} 实际 {actual_name}"
            )

    if not API_PREFIX:
        problems.append("契约缺少 API 前缀")
    return problems


def main() -> int:
    from app.main import create_app

    schema = create_app().openapi()
    problems = collect_drift(schema)
    if problems:
        print("检测到契约漂移：")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"契约一致：{len(OPERATIONS)} 个操作与 tech/flowstudio_contracts 的操作表匹配。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
