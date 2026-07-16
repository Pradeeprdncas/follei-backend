from typing import Any

from pydantic import BaseModel, Field


class CreateToolRequest(BaseModel):
    name: str = Field(examples=["crm_search_contacts"])
    display_name: str = Field(examples=["Search Contacts"])
    description: str | None = Field(default=None, examples=["Search for contacts in the CRM"])
    category: str = Field(examples=["crm"])
    tenant_id: str = Field(examples=["11111111-1111-4111-8111-111111111111"])
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    auth_required: bool = True
    rate_limit: dict[str, Any] = Field(default_factory=dict, examples=[{"requests_per_minute": 60}])


class ToolSummary(BaseModel):
    id: str
    name: str
    display_name: str
    category: str


class ToolResponse(ToolSummary):
    description: str | None = None
    tenant_id: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    auth_required: bool
    rate_limit: dict[str, Any] = Field(default_factory=dict)
    executions_count: int = 0
    avg_latency_ms: int = 0
    success_rate: float = 1.0
    created_at: str


class ToolListResponse(BaseModel):
    items: list[ToolSummary]
    total: int
    page: int
    page_size: int


class ExecuteToolRequest(BaseModel):
    agent_id: str = Field(examples=["22222222-2222-4222-8222-222222222222"])
    conversation_id: str | None = Field(default=None, examples=["33333333-3333-4333-8333-333333333333"])
    parameters: dict[str, Any] = Field(default_factory=dict, examples=[{"query": "Acme Corp", "limit": 5}])
    context: dict[str, Any] = Field(default_factory=dict, examples=[{"tenant_id": "11111111-1111-4111-8111-111111111111"}])


class ToolExecutionResponse(BaseModel):
    id: str
    tool_id: str
    tool_name: str
    agent_id: str | None = None
    conversation_id: str | None = None
    status: str
    result: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int
    tokens_used: int = 0
    created_at: str


class ToolExecutionListResponse(BaseModel):
    items: list[ToolExecutionResponse]
    total: int
    page: int
    page_size: int


class ToolPermissionRequest(BaseModel):
    agent_id: str = Field(examples=["22222222-2222-4222-8222-222222222222"])
    permission: str = Field(default="execute", examples=["execute"])
    constraints: dict[str, Any] = Field(default_factory=dict, examples=[{"max_per_day": 100}])


class ToolPermissionResponse(BaseModel):
    id: str
    tool_id: str
    agent_id: str
    permission: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ConnectorLogResponse(BaseModel):
    id: str
    connector: str
    level: str
    message: str
    timestamp: str


class ConnectorLogListResponse(BaseModel):
    items: list[ConnectorLogResponse]
    total: int
    page: int
    page_size: int
