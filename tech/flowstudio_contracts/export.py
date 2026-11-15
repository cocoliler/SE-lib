"""契约导出：Pydantic 模型 → JSON Schema / OpenAPI 3.1 / TypeScript 类型。

所有产物都是纯函数结果，便于 `--check` 模式在 CI 中比对漂移。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel

from .api import OPERATIONS, operation_path
from .codes import ERROR_HTTP_STATUS, ErrorCode
from .constants import PAGE_SIZE_MAX, RULES_VERSION, SCHEMA_VERSION
from .registry import exported_models, referenced_models
from .samples import fixture_json

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
ARTIFACTS_DIR = "tech/artifacts"
TS_OUTPUT_PATH = "frontend/src/api/generated/contracts.ts"
OPENAPI_PATH = f"{ARTIFACTS_DIR}/openapi.json"
MANIFEST_PATH = f"{ARTIFACTS_DIR}/manifest.json"
_IDENTIFIER_IN_TS = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_TS_RESERVED = frozenset(
    {
        "break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do",
        "else", "enum", "export", "extends", "false", "finally", "for", "function", "if", "import", "in",
        "instanceof", "new", "null", "return", "super", "switch", "this", "throw", "true", "try", "typeof",
        "var", "void", "while", "with", "as", "implements", "interface", "let", "package", "private",
        "protected", "public", "static", "yield",
    }
)


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """独立 Schema 文件：自包含 $defs，可被 jsonschema 等通用校验器直接使用。"""
    schema = model.model_json_schema(ref_template="#/$defs/{model}")
    schema["$schema"] = JSON_SCHEMA_DIALECT
    return schema


def _error_status_map(codes: tuple[ErrorCode, ...]) -> dict[int, list[ErrorCode]]:
    grouped: dict[int, list[ErrorCode]] = {}
    for code in codes:
        status = ERROR_HTTP_STATUS.get(code)
        if status is None:  # pragma: no cover - ErrorCode 必须全部登记状态
            raise KeyError(f"错误码 {code} 缺少 HTTP 状态映射")
        grouped.setdefault(status, []).append(code)
    return dict(sorted(grouped.items()))


def _path_parameters(path: str) -> list[str]:
    return re.findall(r"\{([a-z_]+)\}", path)


def openapi_document() -> dict[str, Any]:
    components: dict[str, Any] = {}
    for model in referenced_models():
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        components.update(schema.pop("$defs", {}))
        components[model.__name__] = schema

    paths: dict[str, Any] = {}
    for operation in OPERATIONS:
        parameters: list[dict[str, Any]] = [
            {
                "name": name,
                "in": "path",
                "required": True,
                "description": "UUID",
                "schema": {"type": "string", "format": "uuid"},
            }
            for name in _path_parameters(operation.path)
        ]
        for name, description in operation.parameters:
            if name == "limit":
                parameters.append(
                    {
                        "name": name,
                        "in": "query",
                        "required": False,
                        "description": description,
                        "schema": {"type": "integer", "minimum": 1, "maximum": PAGE_SIZE_MAX},
                    }
                )
            else:
                parameters.append(
                    {
                        "name": name,
                        "in": "query",
                        "required": False,
                        "description": description,
                        "schema": {"type": "string"},
                    }
                )
        if operation.method != "get":
            parameters.append(
                {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "description": "写命令幂等键（UUID 字符串）；同键异内容返回 409",
                    "schema": {"type": "string", "format": "uuid"},
                }
            )

        success: dict[str, Any] = {"description": f"{operation.success_status} 成功"}
        if operation.response_model is not None:
            success["content"] = {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{operation.response_model.__name__}"}
                }
            }
        responses: dict[str, Any] = {str(operation.success_status): success}
        for status, codes in _error_status_map(operation.error_codes).items():
            responses[str(status)] = {
                "description": "、".join(code.value for code in codes),
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}},
            }

        body: dict[str, Any] = {
            "tags": list(operation.tags),
            "operationId": operation.operation_id,
            "summary": operation.summary,
            "responses": responses,
        }
        if parameters:
            body["parameters"] = parameters
        if operation.request_model is not None:
            body["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{operation.request_model.__name__}"}}
                },
            }
        paths.setdefault(operation_path(operation), {})[operation.method] = body

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "FlowStudio Planning API",
            "version": SCHEMA_VERSION,
            "description": (
                "通用设计规格 → PM Agent 任务分解 → 确定性编排 → 可视化 的规划闭环接口契约。"
                "写入拒绝未知字段；坐标与注释不参与业务顺序；PlanningRun 与未来执行 Run 不合并。"
            ),
            "x-rules-version": RULES_VERSION,
        },
        "servers": [{"url": "http://127.0.0.1:8000", "description": "本地单体，仅监听 loopback"}],
        "paths": dict(sorted(paths.items())),
        "components": {"schemas": dict(sorted(components.items()))},
    }


def _ts_key(name: str) -> str:
    if _IDENTIFIER_IN_TS.match(name) and name not in _TS_RESERVED:
        return name
    return json.dumps(name, ensure_ascii=False)


def _ts_literal(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _ts_type(schema: dict[str, Any], indent: int = 0) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "const" in schema:
        return _ts_literal(schema["const"])
    if "enum" in schema:
        return " | ".join(_ts_literal(item) for item in schema["enum"])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            parts = list(dict.fromkeys(_ts_type(item, indent) for item in schema[key]))
            return " | ".join(parts)
    if "allOf" in schema:
        return " & ".join(_ts_type(item, indent) for item in schema["allOf"])

    declared = schema.get("type")
    if isinstance(declared, list):
        return " | ".join(dict.fromkeys(_ts_type({**schema, "type": item}, indent) for item in declared))
    if declared == "array":
        item_type = _ts_type(schema.get("items", {}), indent)
        return f"({item_type})[]" if "|" in item_type else f"{item_type}[]"
    if "patternProperties" in schema:
        pattern_properties = list(schema["patternProperties"].values())
        value_type = _ts_type(pattern_properties[0], indent) if len(pattern_properties) == 1 else "unknown"
        return f"Record<string, {value_type}>"
    if declared == "object" or "properties" in schema:
        properties = schema.get("properties")
        if not properties:
            additional = schema.get("additionalProperties")
            if additional is False:
                return "Record<string, never>"
            if isinstance(additional, dict):
                return f"Record<string, {_ts_type(additional, indent)}>"
            return "Record<string, unknown>"
        required = set(schema.get("required", []))
        padding = "  " * (indent + 1)
        lines = ["{"]
        for name, value in properties.items():
            optional = "" if name in required else "?"
            lines.append(f"{padding}{_ts_key(name)}{optional}: {_ts_type(value, indent + 1)};")
        lines.append(f"{'  ' * indent}}}")
        return "\n".join(lines)
    if declared == "string":
        return "string"
    if declared in ("integer", "number"):
        return "number"
    if declared == "boolean":
        return "boolean"
    if declared == "null":
        return "null"
    return "unknown"


def typescript_module() -> str:
    pool: dict[str, dict[str, Any]] = {}
    for model in referenced_models():
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        pool.update(schema.pop("$defs", {}))
        pool[model.__name__] = schema

    lines = [
        "// 本文件由 tech/scripts/export_contracts.py 自动生成，请勿手改。",
        "// 重新生成：python tech/scripts/export_contracts.py",
        f'export const SCHEMA_VERSION = "{SCHEMA_VERSION}";',
        f'export const RULES_VERSION = "{RULES_VERSION}";',
        "",
    ]
    for name in sorted(pool):
        lines.append(f"export type {name} = {_ts_type(pool[name])};")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def build_artifacts() -> dict[str, str]:
    """返回 {仓库相对路径: 文件内容}，写入与漂移检查共用。"""
    artifacts: dict[str, str] = {}
    for name, model in exported_models().items():
        artifacts[f"{ARTIFACTS_DIR}/schema/{name}.schema.json"] = dumps(json_schema(model))
    artifacts[OPENAPI_PATH] = dumps(openapi_document())
    artifacts[TS_OUTPUT_PATH] = typescript_module()
    for name, content in fixture_json().items():
        artifacts[f"{ARTIFACTS_DIR}/examples/{name}.json"] = content

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "generator": "tech/scripts/export_contracts.py",
        "files": {
            path: hashlib.sha256(content.encode("utf-8")).hexdigest() for path, content in sorted(artifacts.items())
        },
    }
    artifacts[MANIFEST_PATH] = dumps(manifest)
    return artifacts


__all__ = [
    "ARTIFACTS_DIR",
    "OPENAPI_PATH",
    "MANIFEST_PATH",
    "TS_OUTPUT_PATH",
    "build_artifacts",
    "dumps",
    "json_schema",
    "openapi_document",
    "typescript_module",
]
