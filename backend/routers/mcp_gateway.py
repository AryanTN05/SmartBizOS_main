"""
routers/mcp_gateway.py — In-house MCP gateway (~100 lines, per spec).

The Foundation research memo committed to building the gateway in-house
("auth → session UUID → namespace prefix → fan-out tools/list, passthrough
tools/call. NOT using MetaMCP / ContextForge / etc.").

This is the V0 implementation: a single FastAPI router that exposes the
two MCP-shaped HTTP endpoints clients need.

  GET  /api/mcp/tools/list                — namespaced tool registry from every module
  POST /api/mcp/tools/call                — invoke a tool by namespaced name

The actual MCP transport (JSON-RPC over stdio, SSE) is *not* implemented here
— SmartBiz uses HTTP-shaped MCP because all our consumers are server-side
(Lara, automations) within the same FastAPI app. When we ship the
public-facing MCP surface, this gateway grows a /api/mcp/sse handler in front
of the same registry.

Module registration:
  Each module exposes (registry: list[dict], functions: dict[str, callable])
  via a `register_mcp_tools()` helper. Currently only Lara registers; the
  rest will hook in as their service layers land.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Tuple

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/mcp", tags=["MCP Gateway"])


# ─────────────────────────────────────────
# Module registration — discovered at import time
# ─────────────────────────────────────────

ToolFn = Callable[..., Awaitable[Any] | Any]
ModuleRegistry = Tuple[List[Dict[str, Any]], Dict[str, ToolFn]]


def _load_modules() -> Dict[str, ModuleRegistry]:
    """Discover modules that expose an MCP tool registry. Lazy-imported so
    this gateway boots even if a module is broken or missing."""
    out: Dict[str, ModuleRegistry] = {}

    # Lara — already exposes get_tool_registry() and TOOL_FUNCTIONS.
    try:
        from lara_smartbiz.tools import get_tool_registry, TOOL_FUNCTIONS
        out["lara"] = (get_tool_registry(), TOOL_FUNCTIONS)
    except Exception as e:  # noqa: BLE001 — defensive, gateway must always boot
        import logging
        logging.getLogger("smartbiz.mcp").warning("lara tools not loaded: %s", e)

    # Future hookups — keep the pattern uniform:
    # try:
    #     from automations.mcp_tools import REGISTRY, FUNCTIONS
    #     out["automation"] = (REGISTRY, FUNCTIONS)
    # except Exception: ...

    return out


_MODULES: Dict[str, ModuleRegistry] = _load_modules()


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────

@router.get("/tools/list")
async def tools_list() -> dict:
    """Concatenate all module tool registries with `<module>.` namespace."""
    items: list[dict] = []
    for module, (registry, _funcs) in _MODULES.items():
        for tool in registry:
            namespaced = dict(tool)
            namespaced["name"] = f"{module}.{tool['name']}"
            namespaced["_module"] = module
            items.append(namespaced)
    return {"items": items, "modules": list(_MODULES.keys())}


@router.post("/tools/call")
async def tools_call(body: dict) -> dict:
    """
    Invoke a namespaced tool. Body shape: { name: "<module>.<tool>", arguments: {...} }
    """
    name = (body or {}).get("name")
    args = (body or {}).get("arguments") or {}
    if not name or "." not in name:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_failed",
                    "message": "name must be '<module>.<tool>'"},
        )
    module, tool_name = name.split(".", 1)
    pair = _MODULES.get(module)
    if not pair:
        raise HTTPException(status_code=404,
                            detail={"code": "not_found",
                                    "message": f"unknown module '{module}'"})
    _registry, funcs = pair
    fn = funcs.get(tool_name)
    if not fn:
        raise HTTPException(status_code=404,
                            detail={"code": "not_found",
                                    "message": f"unknown tool '{tool_name}' in module '{module}'"})

    try:
        result = fn(**args)
        if hasattr(result, "__await__"):
            result = await result
    except TypeError as e:
        # Argument mismatch — surface a 422 so callers can correct.
        raise HTTPException(status_code=422,
                            detail={"code": "validation_failed",
                                    "message": f"argument mismatch: {e}"}) from e
    return {"name": name, "result": result}
