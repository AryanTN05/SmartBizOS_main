"""Tests for the in-house MCP gateway."""


def test_tools_list_returns_namespaced_lara_tools(client):
    body = client.get("/api/mcp/tools/list").json()
    assert "items" in body and body["items"]
    assert "lara" in body["modules"]
    # Every tool name must be `<module>.<tool>` form.
    assert all("." in t["name"] for t in body["items"])
    # At least one canonical Lara tool must be present.
    names = {t["name"] for t in body["items"]}
    assert "lara.show_artifact" in names


def test_tools_call_dispatches_sync_tool(client):
    r = client.post("/api/mcp/tools/call", json={
        "name": "lara.show_artifact",
        "arguments": {"url": "", "table": "<p>x</p>", "charts": ""},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "lara.show_artifact"
    assert "result" in body


def test_tools_call_unknown_module_404(client):
    r = client.post("/api/mcp/tools/call", json={
        "name": "fintech.get_invoices", "arguments": {},
    })
    assert r.status_code == 404


def test_tools_call_unknown_tool_404(client):
    r = client.post("/api/mcp/tools/call", json={
        "name": "lara.nope", "arguments": {},
    })
    assert r.status_code == 404


def test_tools_call_missing_dot_422(client):
    r = client.post("/api/mcp/tools/call", json={"name": "no_dot"})
    assert r.status_code == 422
