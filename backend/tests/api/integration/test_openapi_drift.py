"""契约漂移回归：路由集合与成功响应必须与 T01 操作表一致。"""

from __future__ import annotations

from tools.export_openapi import collect_drift


def test_openapi_matches_contract_operations(client) -> None:
    schema = client.app.openapi()
    assert collect_drift(schema) == []
