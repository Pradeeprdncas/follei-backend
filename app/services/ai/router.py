"""AI Router - Refactored to use ModelManager, Planner, and MCP Adapter.

Routes AI requests through:
AI Router → Planner → [RAG | MCP | Database | CRM | Agent | Direct Generation]
              ↓
         ModelManager → Loaded Model
"""
from typing import Any, Dict, List, Optional
from loguru import logger
from app.services.ai.model_manager import get_model_manager
from app.services.ai.cache import get_response_cache
from app.services.ai.planner import get_ai_planner, ExecutionPath
from app.services.ai.mcp_adapter import get_mcp_adapter


class AIRouter:
    """Central router for all AI operations.
    
    Uses ModelManager for model lifecycle.
    Uses Planner for intelligent routing.
    Uses MCP Adapter for tool execution.
    Never instantiates models directly.
    """
    
    def __init__(self):
        """Initialize AI router."""
        self._model_manager = get_model_manager()
        self._cache = get_response_cache()
        self._planner = get_ai_planner()
        self._mcp_adapter = get_mcp_adapter()
        logger.info("AI Router initialized (using ModelManager + Planner + MCP Adapter)")
    
    async def process_request(
        self,
        query: str,
        context: Dict[str, Any] = None,
        user_intent: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Process a user request through the AI architecture.
        
        Fast-path: pure RAG/knowledge queries skip the planner entirely.
        """
        context = context or {}
        user_intent = user_intent or {}

        try:
            # Fast-path: detect pure knowledge query, skip planner
            q = query.lower().strip()
            _rag_keywords = ("what", "how", "why", "explain", "describe",
                             "summarize", "find", "search", "document",
                             "policy", "procedure")
            is_knowledge_query = any(kw in q.split() for kw in _rag_keywords)

            if is_knowledge_query or not any(kw in q for kw in
                ("send", "create", "schedule", "book", "email", "crm",
                 "agent", "list", "show", "count")):
                return await self._execute_rag(query, context, {})

            # Planner only for non-RAG paths
            plan = await self._planner.plan(query, context, user_intent)
            primary_path = plan.get("primary_path")

            logger.info(f"Processing request via: {primary_path}")

            if primary_path == ExecutionPath.RAG.value:
                return await self._execute_rag(query, context, plan)
            elif primary_path == ExecutionPath.MCP.value:
                return await self._execute_mcp(query, context, plan)
            elif primary_path == ExecutionPath.DATABASE.value:
                return await self._execute_database(query, context, plan)
            elif primary_path == ExecutionPath.CRM.value:
                return await self._execute_crm(query, context, plan)
            elif primary_path == ExecutionPath.AGENT.value:
                return await self._execute_agent(query, context, plan)
            elif primary_path == ExecutionPath.DIRECT_GENERATION.value:
                return await self._execute_direct_generation(query, context, plan)
            else:
                logger.warning(f"Unknown execution path: {primary_path}, falling back to RAG")
                return await self._execute_rag(query, context, plan)

        except Exception as e:
            logger.error(f"Request processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "execution_path": "error"
            }
    
    async def _execute_rag(self, query: str, context: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute RAG pipeline (fast-path, planner already decided RAG)."""
        try:
            from app.services.rag.pipelines.chat import chat_pipeline

            result = await chat_pipeline(
                question=query,
                tenant_id=context.get("tenant_id", "default"),
                session_id=context.get("session_id")
            )

            return {
                "success": True,
                "answer": result.get("answer"),
                "citations": result.get("citations", []),
                "confidence": result.get("confidence", 0.0),
                "supported": result.get("supported", False),
                "execution_path": "rag",
            }

        except Exception as e:
            logger.error(f"RAG execution failed: {e}")
            raise RuntimeError(f"RAG execution failed: {e}") from e
    
    async def _execute_mcp(self, query: str, context: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute MCP tools.
        
        Args:
            query: User query
            context: Execution context
            plan: Execution plan
            
        Returns:
            MCP execution result
        """
        try:
            # Initialize MCP adapter if needed
            if not self._mcp_adapter._initialized:
                await self._mcp_adapter.initialize()
            
            # Get suggested tools from plan
            suggested_tools = plan.get("suggested_tools", [])
            
            if not suggested_tools:
                # If no specific tools suggested, use direct generation
                return await self._execute_direct_generation(query, context, plan)
            
            # Execute tools
            tool_results = []
            for tool_name in suggested_tools:
                # Validate tool
                validation = await self._mcp_adapter.validate_tool(tool_name, {})
                if not validation.get("valid"):
                    logger.warning(f"Tool {tool_name} validation failed: {validation.get('error')}")
                    continue
                
                # Execute tool
                result = await self._mcp_adapter.execute_tool(
                    tool_name=tool_name,
                    parameters={},
                    context=context,
                    timeout=30.0,
                    max_retries=2
                )
                
                tool_results.append(result)
            
            # Generate response from tool results
            response_text = self._format_tool_results(tool_results)
            
            return {
                "success": True,
                "answer": response_text,
                "tool_results": tool_results,
                "execution_path": "mcp",
                "plan": plan
            }
            
        except Exception as e:
            logger.error(f"MCP execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_path": "mcp",
                "plan": plan
            }
    
    async def _execute_database(self, query: str, context: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute database query.
        
        Args:
            query: User query
            context: Execution context
            plan: Execution plan
            
        Returns:
            Database query result
        """
        try:
            # TODO: Implement database query execution
            # For now, fallback to RAG
            logger.warning("Database execution not yet implemented, falling back to RAG")
            return await self._execute_rag(query, context, plan)
            
        except Exception as e:
            logger.error(f"Database execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_path": "database"
            }
    
    async def _execute_crm(self, query: str, context: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute CRM operation.
        
        Args:
            query: User query
            context: Execution context
            plan: Execution plan
            
        Returns:
            CRM operation result
        """
        try:
            # TODO: Implement CRM operation execution
            # For now, fallback to RAG
            logger.warning("CRM execution not yet implemented, falling back to RAG")
            return await self._execute_rag(query, context, plan)
            
        except Exception as e:
            logger.error(f"CRM execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_path": "crm"
            }
    
    async def _execute_agent(self, query: str, context: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent workflow.
        
        Args:
            query: User query
            context: Execution context
            plan: Execution plan
            
        Returns:
            Agent execution result
        """
        try:
            # TODO: Implement agent execution
            # For now, fallback to RAG
            logger.warning("Agent execution not yet implemented, falling back to RAG")
            return await self._execute_rag(query, context, plan)
            
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_path": "agent"
            }
    
    async def _execute_direct_generation(self, query: str, context: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute direct generation (no RAG).
        
        Args:
            query: User query
            context: Execution context
            plan: Execution plan
            
        Returns:
            Generated response
        """
        try:
            # Use AI Router for direct generation
            answer = await self.generate(
                prompt=query,
                system_prompt="You are a helpful assistant.",
                use_cache=True
            )
            
            return {
                "success": True,
                "answer": answer,
                "execution_path": "direct_generation",
                "plan": plan
            }
            
        except Exception as e:
            logger.error(f"Direct generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_path": "direct_generation"
            }
    
    def _format_tool_results(self, tool_results: List[Dict[str, Any]]) -> str:
        """Format tool results into human-readable response.
        
        Args:
            tool_results: List of tool execution results
            
        Returns:
            Formatted response text
        """
        if not tool_results:
            return "No tools were executed."
        
        parts = []
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get("tool", "unknown")
            success = result.get("success", False)
            
            if success:
                tool_result = result.get("result", {})
                parts.append(f"{i}. {tool_name}: {tool_result}")
            else:
                error = result.get("message", "Unknown error")
                parts.append(f"{i}. {tool_name}: Failed - {error}")
        
        return "\n".join(parts)
    
    # All model operations delegate to AIGateway (single inference path)
    async def embed_texts(self, texts: List[str], use_cache: bool = True) -> List[List[float]]:
        from app.services.ai.gateway import get_ai_gateway
        return await get_ai_gateway().embed_texts(texts, use_cache=use_cache)

    async def embed_query(self, text: str, use_cache: bool = True) -> List[float]:
        from app.services.ai.gateway import get_ai_gateway
        return await get_ai_gateway().embed_query(text, use_cache=use_cache)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        use_cache: bool = False,
        **kwargs
    ) -> str:
        from app.services.ai.gateway import get_ai_gateway
        return await get_ai_gateway().generate(
            prompt=prompt, system_prompt=system_prompt,
            max_tokens=max_tokens, temperature=temperature,
            use_cache=use_cache,
        )

    async def verify(self, question: str, context: str, answer: str, use_cache: bool = True) -> Dict[str, Any]:
        from app.services.ai.gateway import get_ai_gateway
        return await get_ai_gateway().verify(question, answer, context, use_cache=use_cache)

    async def rerank(self, query: str, documents: List[str], top_k: int = 5, use_cache: bool = True) -> List[Dict[str, Any]]:
        from app.services.ai.gateway import get_ai_gateway
        return await get_ai_gateway().rerank(query, documents, top_k, use_cache=use_cache)

    async def summarize(self, text: str, max_length: int = 200, use_cache: bool = True) -> str:
        from app.services.ai.gateway import get_ai_gateway
        return await get_ai_gateway().summarize(text, max_length, use_cache=use_cache)

    async def optimize_query(self, query: str, use_cache: bool = True) -> Dict[str, Any]:
        from app.services.ai.gateway import get_ai_gateway
        return await get_ai_gateway().optimize_query(query, use_cache=use_cache)
    
    def _fallback_rerank(self, query: str, documents: List[str], top_k: int) -> List[Dict[str, Any]]:
        """Fallback reranking using simple scoring."""
        query_terms = set(query.lower().split())
        
        scored_docs = []
        for idx, doc in enumerate(documents):
            doc_terms = set(doc.lower().split())
            overlap = len(query_terms & doc_terms)
            score = overlap / len(query_terms) if query_terms else 0.0
            
            if query.lower() in doc.lower():
                score += 0.5
            
            scored_docs.append({
                "document": doc,
                "score": min(score, 1.0),
                "index": idx
            })
        
        scored_docs.sort(key=lambda x: x["score"], reverse=True)
        return scored_docs[:top_k]
    
    async def process_auto_reply(
        self,
        message: str,
        tenant_id: str,
        lead_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Generate an auto-reply for an inbound message.

        Used by InboundMessageEngine and BrevoInboundService.
        Runs the RAG pipeline and returns answer + confidence.

        Args:
            message: Inbound message text.
            tenant_id: Tenant UUID.
            lead_id: Lead UUID.

        Returns:
            dict with answer, confidence, intent or None on failure.
        """
        try:
            result = await self.process_request(
                query=message,
                context={"tenant_id": tenant_id, "lead_id": lead_id},
                user_intent={"source": "auto_reply"},
            )
            if result.get("success"):
                return {
                    "answer": result.get("answer"),
                    "confidence": result.get("confidence", 0.0),
                    "intent": result.get("intent"),
                    "citations": result.get("citations", []),
                    "execution_path": result.get("execution_path", "rag"),
                }
            logger.warning(f"Auto-reply generation failed: {result.get('error')}")
            return None
        except Exception as e:
            logger.error(f"Auto-reply generation error: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics."""
        return {
            "model_manager": self._model_manager.get_loaded_models(),
            "cache": self._cache.get_stats(),
            "planner": "active",
            "mcp_adapter": self._mcp_adapter.get_metrics() if self._mcp_adapter._initialized else "not_initialized"
        }


# Singleton router instance
_router: Optional[AIRouter] = None


def get_ai_router() -> AIRouter:
    """Get or create the singleton AI router."""
    global _router
    if _router is None:
        _router = AIRouter()
    return _router


# Dependency injection for FastAPI
async def get_ai_service() -> AIRouter:
    """FastAPI dependency to get AI service."""
    return get_ai_router()