"""AI Planner - Intelligent routing of requests to appropriate services.

The Planner analyzes user requests and decides the best execution path:
- RAG (Retrieval Augmented Generation)
- MCP (Model Context Protocol - tools)
- Database queries
- CRM operations
- API calls
- Agent execution
- Direct generation
"""
from typing import Dict, Any, List
from enum import Enum
from loguru import logger


class ExecutionPath(Enum):
    """Available execution paths for AI requests."""
    RAG = "rag"
    MCP = "mcp"
    DATABASE = "database"
    CRM = "crm"
    API = "api"
    TOOL = "tool"
    AGENT = "agent"
    DIRECT_GENERATION = "direct_generation"
    HYBRID = "hybrid"  # Combination of multiple paths


class AIPlanner:
    """Plans execution path for AI requests.
    
    Analyzes user intent and context to determine:
    - Whether to use RAG (knowledge base)
    - Whether to use MCP (external tools)
    - Whether to query database directly
    - Whether to invoke an agent
    - Whether to use direct generation
    
    The Planner is the ONLY component that can request tool execution.
    The Generator never invokes tools directly.
    """
    
    def __init__(self):
        """Initialize planner."""
        self._intent_keywords = {
            ExecutionPath.RAG: [
                "what", "how", "why", "when", "where", "who", "explain",
                "describe", "summarize", "find", "search", "lookup",
                "document", "policy", "procedure", "faq", "knowledge"
            ],
            ExecutionPath.MCP: [
                "send email", "create event", "schedule", "book",
                "contact", "message", "notify", "alert", "remind",
                "gmail", "outlook", "calendar", "whatsapp", "slack",
                "create meeting", "send message", "book appointment"
            ],
            ExecutionPath.DATABASE: [
                "list", "show", "get", "retrieve", "count",
                "leads", "customers", "conversations", "messages",
                "subscriptions", "invoices", "payments"
            ],
            ExecutionPath.CRM: [
                "crm", "hubspot", "salesforce", "zoho",
                "opportunity", "deal", "contact", "account"
            ],
            ExecutionPath.AGENT: [
                "agent", "execute", "run", "perform", "automate",
                "workflow", "task", "action", "multi-step"
            ],
            ExecutionPath.TOOL: [
                "tool", "use tool", "execute tool", "call"
            ]
        }
    
    async def plan(
        self,
        query: str,
        context: Dict[str, Any] = None,
        user_intent: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Plan execution path for a request.
        
        Args:
            query: User query
            context: Additional context (tenant_id, user_id, etc.)
            user_intent: Intent classification result (if available)
            
        Returns:
            Execution plan with path and parameters
        """
        context = context or {}
        user_intent = user_intent or {}
        
        # Analyze query
        query_lower = query.lower()
        
        # Check for explicit tool/MCP requests (HIGHEST PRIORITY)
        mcp_keywords = ["send email", "create event", "schedule", "book",
                       "contact", "message", "notify", "alert", "remind",
                       "gmail", "outlook", "calendar", "whatsapp", "slack",
                       "create meeting", "send message", "book appointment"]
        
        if any(keyword in query_lower for keyword in mcp_keywords):
            return self._create_mcp_plan(query, context)
        
        # Check for database queries
        db_keywords = ["list", "show", "get", "retrieve", "count", "how many"]
        entity_keywords = ["lead", "customer", "conversation", "message",
                          "subscription", "invoice", "payment"]
        
        if (any(keyword in query_lower for keyword in db_keywords) and
            any(keyword in query_lower for keyword in entity_keywords)):
            return self._create_plan(ExecutionPath.DATABASE, query, context)
        
        # Check for CRM operations
        crm_keywords = ["crm", "hubspot", "salesforce", "zoho", 
                       "opportunity", "deal", "account"]
        
        if any(keyword in query_lower for keyword in crm_keywords):
            return self._create_plan(ExecutionPath.CRM, query, context)
        
        # Check for agent tasks
        agent_keywords = ["agent", "execute", "run", "automate", "workflow",
                         "task", "action", "multi-step"]
        
        if any(keyword in query_lower for keyword in agent_keywords):
            return self._create_plan(ExecutionPath.AGENT, query, context)
        
        # Check for knowledge questions (default to RAG)
        rag_keywords = ["what", "how", "why", "explain", "describe", "summarize",
                       "find", "search", "document", "policy", "procedure"]
        
        if any(keyword in query_lower for keyword in rag_keywords):
            return self._create_plan(ExecutionPath.RAG, query, context)
        
        # Use intent classification if available
        intent = user_intent.get("intent", "general_query")
        
        if intent in ["support_request", "technical_issue"]:
            return self._create_plan(ExecutionPath.RAG, query, context)
        
        if intent in ["sales_inquiry", "lead_qualification"]:
            return self._create_hybrid_plan(
                query, context,
                primary=ExecutionPath.RAG,
                secondary=ExecutionPath.CRM
            )
        
        # Default to RAG
        return self._create_plan(ExecutionPath.RAG, query, context)
    
    def _create_mcp_plan(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Create execution plan for MCP tool execution.
        
        Args:
            query: User query
            context: Additional context
            
        Returns:
            Execution plan
        """
        # Determine which MCP tools might be needed
        query_lower = query.lower()
        suggested_tools = []
        
        if any(kw in query_lower for kw in ["email", "gmail", "outlook"]):
            suggested_tools.append("send_email")
        if any(kw in query_lower for kw in ["calendar", "event", "schedule", "meeting"]):
            suggested_tools.append("create_event")
        if any(kw in query_lower for kw in ["whatsapp", "message", "chat"]):
            suggested_tools.append("send_whatsapp_message")
        if any(kw in query_lower for kw in ["crm", "contact", "lead"]):
            suggested_tools.append("crm_create_contact")
        
        return {
            "primary_path": ExecutionPath.MCP.value,
            "query": query,
            "context": context,
            "confidence": 1.0,
            "reasoning": "Query requires external tool execution",
            "suggested_tools": suggested_tools,
            "fallback": ExecutionPath.DIRECT_GENERATION.value
        }
    
    def _create_hybrid_plan(
        self,
        query: str,
        context: Dict[str, Any],
        primary: ExecutionPath,
        secondary: ExecutionPath
    ) -> Dict[str, Any]:
        """Create hybrid execution plan.
        
        Args:
            query: User query
            context: Additional context
            primary: Primary execution path
            secondary: Secondary execution path
            
        Returns:
            Execution plan
        """
        return {
            "primary_path": primary.value,
            "secondary_paths": [secondary.value],
            "query": query,
            "context": context,
            "confidence": 0.8,
            "reasoning": f"Hybrid approach: {primary.value} + {secondary.value}",
            "fallback": ExecutionPath.RAG.value
        }
    
    def _create_plan(
        self,
        primary_path: ExecutionPath,
        query: str,
        context: Dict[str, Any],
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create execution plan.
        
        Args:
            primary_path: Primary execution path
            query: User query
            context: Additional context
            options: Additional options
            
        Returns:
            Execution plan
        """
        plan = {
            "primary_path": primary_path.value,
            "query": query,
            "context": context,
            "confidence": 1.0,
            "reasoning": f"Query matches {primary_path.value} pattern",
        }
        
        if options:
            plan.update(options)
        
        # Add fallback paths
        if primary_path == ExecutionPath.RAG:
            plan["fallback"] = ExecutionPath.DIRECT_GENERATION.value
        elif primary_path == ExecutionPath.MCP:
            plan["fallback"] = ExecutionPath.DIRECT_GENERATION.value
        elif primary_path == ExecutionPath.HYBRID:
            plan["fallback"] = ExecutionPath.RAG.value
        elif primary_path == ExecutionPath.DATABASE:
            plan["fallback"] = ExecutionPath.RAG.value
        elif primary_path == ExecutionPath.CRM:
            plan["fallback"] = ExecutionPath.DATABASE.value
        elif primary_path == ExecutionPath.AGENT:
            plan["fallback"] = ExecutionPath.RAG.value
        
        logger.info(f"Execution plan: {plan['primary_path']} (confidence: {plan['confidence']})")
        return plan
    
    async def should_use_rag(self, query: str, context: Dict[str, Any] = None) -> bool:
        """Determine if RAG should be used."""
        plan = await self.plan(query, context)
        return plan["primary_path"] in [ExecutionPath.RAG.value, ExecutionPath.HYBRID.value]
    
    async def should_use_mcp(self, query: str, context: Dict[str, Any] = None) -> bool:
        """Determine if MCP should be used."""
        plan = await self.plan(query, context)
        return plan["primary_path"] == ExecutionPath.MCP.value
    
    async def should_use_agent(self, query: str, context: Dict[str, Any] = None) -> bool:
        """Determine if agent should be used."""
        plan = await self.plan(query, context)
        return plan["primary_path"] == ExecutionPath.AGENT.value
    
    async def get_suggested_tools(self, query: str, context: Dict[str, Any] = None) -> List[str]:
        """Get suggested MCP tools for a query.
        
        Args:
            query: User query
            context: Additional context
            
        Returns:
            List of suggested tool names
        """
        plan = await self.plan(query, context)
        return plan.get("suggested_tools", [])


# Singleton instance
_planner = None


def get_ai_planner() -> AIPlanner:
    """Get or create the singleton AIPlanner.
    
    Returns:
        AIPlanner instance
    """
    global _planner
    if _planner is None:
        _planner = AIPlanner()
    return _planner