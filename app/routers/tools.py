import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.tool import (
    ConnectorLogListResponse,
    ConnectorLogResponse,
    CreateToolRequest,
    ExecuteToolRequest,
    ToolExecutionListResponse,
    ToolExecutionResponse,
    ToolListResponse,
    ToolPermissionRequest,
    ToolPermissionResponse,
    ToolResponse,
    ToolSummary,
)

tools_router = APIRouter(prefix="/tools", tags=["Tools, MCP & Registry"])
executions_router = APIRouter(prefix="/tool-executions", tags=["Tools, MCP & Registry"])
logs_router = APIRouter(prefix="/connector-logs", tags=["Tools, MCP & Registry"])

TOOLS: dict[str, ToolResponse] = {}
EXECUTIONS: dict[str, ToolExecutionResponse] = {}
PERMISSIONS: dict[str, ToolPermissionResponse] = {}
CONNECTOR_LOGS: dict[str, ConnectorLogResponse] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_tool_or_404(tool_id: str) -> ToolResponse:
    tool = TOOLS.get(tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool


def _seed_log(connector: str, level: str, message: str) -> None:
    log_id = str(uuid4())
    CONNECTOR_LOGS[log_id] = ConnectorLogResponse(
        id=log_id,
        connector=connector,
        level=level,
        message=message,
        timestamp=_now(),
    )


@tools_router.post("", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
def create_tool(payload: CreateToolRequest) -> ToolResponse:
    tool_id = str(uuid4())
    tool = ToolResponse(id=tool_id, executions_count=0, avg_latency_ms=0, success_rate=1.0, created_at=_now(), **payload.model_dump())
    TOOLS[tool_id] = tool
    return tool


@tools_router.get("", response_model=ToolListResponse)
def list_tools(
    category: str | None = None,
    tenant_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ToolListResponse:
    items = [
        ToolSummary(id=item.id, name=item.name, display_name=item.display_name, category=item.category)
        for item in TOOLS.values()
        if (category is None or item.category == category) and (tenant_id is None or item.tenant_id == tenant_id)
    ]
    total = len(items)
    start = (page - 1) * page_size
    return ToolListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@tools_router.get("/{tool_id}", response_model=ToolResponse)
def get_tool(tool_id: str) -> ToolResponse:
    return _get_tool_or_404(tool_id)


@tools_router.post("/{tool_id}/execute", response_model=ToolExecutionResponse)
def execute_tool(tool_id: str, payload: ExecuteToolRequest) -> ToolExecutionResponse:
    start = time.perf_counter()
    tool = _get_tool_or_404(tool_id)
    result = {
        "contacts": [
            {
                "id": str(uuid4()),
                "name": "Jane Lead",
                "company": payload.parameters.get("query", "Acme Corp"),
                "email": "jane@acme.com",
            }
        ]
    }
    latency_ms = max(1, int((time.perf_counter() - start) * 1000))
    execution_id = str(uuid4())
    execution = ToolExecutionResponse(
        id=execution_id,
        tool_id=tool_id,
        tool_name=tool.name,
        agent_id=payload.agent_id,
        conversation_id=payload.conversation_id,
        status="success",
        result=result,
        latency_ms=latency_ms,
        tokens_used=0,
        created_at=_now(),
    )
    EXECUTIONS[execution_id] = execution
    count = tool.executions_count + 1
    avg_latency = int(((tool.avg_latency_ms * tool.executions_count) + latency_ms) / count)
    TOOLS[tool_id] = tool.model_copy(update={"executions_count": count, "avg_latency_ms": avg_latency, "success_rate": 1.0})
    return execution


@executions_router.get("", response_model=ToolExecutionListResponse)
def list_tool_executions(
    tool_id: str | None = None,
    agent_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ToolExecutionListResponse:
    items = list(EXECUTIONS.values())
    if tool_id is not None:
        items = [item for item in items if item.tool_id == tool_id]
    if agent_id is not None:
        items = [item for item in items if item.agent_id == agent_id]
    if status_filter is not None:
        items = [item for item in items if item.status == status_filter]
    total = len(items)
    start = (page - 1) * page_size
    return ToolExecutionListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)


@tools_router.post("/{tool_id}/permissions", response_model=ToolPermissionResponse, status_code=status.HTTP_201_CREATED)
def create_tool_permission(tool_id: str, payload: ToolPermissionRequest) -> ToolPermissionResponse:
    _get_tool_or_404(tool_id)
    permission_id = str(uuid4())
    permission = ToolPermissionResponse(id=permission_id, tool_id=tool_id, created_at=_now(), **payload.model_dump())
    PERMISSIONS[permission_id] = permission
    return permission


@logs_router.get("", response_model=ConnectorLogListResponse)
def list_connector_logs(
    connector: str | None = None,
    level: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConnectorLogListResponse:
    if not CONNECTOR_LOGS:
        _seed_log("whatsapp", "info", "Connector initialized")
        _seed_log("salesforce", "info", "Sync worker ready")
    items = list(CONNECTOR_LOGS.values())
    if connector is not None:
        items = [item for item in items if item.connector == connector]
    if level is not None:
        items = [item for item in items if item.level == level]
    total = len(items)
    start = (page - 1) * page_size
    return ConnectorLogListResponse(items=items[start : start + page_size], total=total, page=page, page_size=page_size)
