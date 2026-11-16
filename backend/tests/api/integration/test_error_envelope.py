"""未知路径也必须返回契约错误信封，而不是 FastAPI 默认的 detail。"""

from __future__ import annotations


def test_unknown_path_returns_contract_envelope(client) -> None:
    response = client.get("/api/v1/nope")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"]
    assert body["error"]["issues"] == []
    assert body["error"]["request_id"]
    assert response.headers["x-request-id"] == body["error"]["request_id"]
