"""Memory Manager - Complete memory architecture for AI system.

Implements:
- Conversation Memory
- Semantic Memory
- Long-Term Memory
- Summarized Memory
- User Memory
- Task Memory

Memory Flow:
Conversation → Memory Retrieval → Planner → Execution
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import deque
from loguru import logger
from app.config.settings import get_settings

_settings = get_settings()


class MemoryManager:
    """Centralized memory management.
    
    Features:
    - Conversation memory (recent messages)
    - Semantic memory (embeddings of important info)
    - Long-term memory (persistent user data)
    - Summarized memory (compressed old conversations)
    - Memory retrieval with ranking
    - Memory pruning and expiration
    """
    
    def __init__(self):
        """Initialize memory manager."""
        # Conversation memory: recent messages per session
        self._conversation_memory: Dict[str, deque] = {}
        self._max_conversation_length = 50  # Keep last 50 messages
        
        # Semantic memory: embeddings of important information
        self._semantic_memory: List[Dict[str, Any]] = []
        self._semantic_embeddings = None
        
        # Long-term memory: persistent user data
        self._long_term_memory: Dict[str, Dict[str, Any]] = {}
        
        # Summarized memory: compressed old conversations
        self._summarized_memory: Dict[str, str] = {}
        
        # User memory: per-user preferences and context
        self._user_memory: Dict[str, Dict[str, Any]] = {}
        
        # Task memory: current task state
        self._task_memory: Dict[str, Dict[str, Any]] = {}
        
        # Memory settings
        self._conversation_ttl = timedelta(hours=24)
        self._semantic_ttl = timedelta(days=7)
        self._long_term_ttl = timedelta(days=30)
        
        logger.info("Memory Manager initialized")
    
    async def get_conversation_context(
        self,
        session_id: str,
        max_messages: int = 10
    ) -> List[Dict[str, str]]:
        """Get recent conversation context.
        
        Args:
            session_id: Session identifier
            max_messages: Maximum messages to return
            
        Returns:
            List of recent messages
        """
        if session_id not in self._conversation_memory:
            return []
        
        messages = list(self._conversation_memory[session_id])
        return messages[-max_messages:]
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> None:
        """Add message to conversation memory.
        
        Args:
            session_id: Session identifier
            role: Message role (user/assistant/system)
            content: Message content
            metadata: Additional metadata
        """
        if session_id not in self._conversation_memory:
            self._conversation_memory[session_id] = deque(
                maxlen=self._max_conversation_length
            )
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        self._conversation_memory[session_id].append(message)
        
        # Also add to long-term memory if important
        if metadata and metadata.get("important", False):
            await self.add_to_semantic_memory(content, metadata)
    
    async def add_to_semantic_memory(
        self,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> None:
        """Add content to semantic memory with embedding.
        
        Args:
            content: Text content
            metadata: Additional metadata
        """
        try:
            # Generate embedding
            from app.services.ai import get_ai_router
            router = get_ai_router()
            embedding = await router.embed_query(content)
            
            memory_item = {
                "content": content,
                "embedding": embedding,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow().isoformat(),
                "access_count": 0
            }
            
            self._semantic_memory.append(memory_item)
            
            # Limit semantic memory size
            if len(self._semantic_memory) > 1000:
                # Remove oldest, least accessed items
                self._semantic_memory.sort(key=lambda x: (x["access_count"], x["timestamp"]))
                self._semantic_memory = self._semantic_memory[100:]
            
            logger.debug(f"Added to semantic memory: {content[:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to add to semantic memory: {e}")
    
    async def retrieve_semantic_memory(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant memories using semantic search.
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of relevant memories
        """
        if not self._semantic_memory:
            return []
        
        try:
            # Generate query embedding
            from app.services.ai import get_ai_router
            router = get_ai_router()
            query_embedding = await router.embed_query(query)
            
            # Calculate similarity scores
            scored_memories = []
            for memory in self._semantic_memory:
                memory_embedding = memory["embedding"]
                score = self._cosine_similarity(query_embedding, memory_embedding)
                
                scored_memories.append({
                    "content": memory["content"],
                    "score": score,
                    "metadata": memory["metadata"],
                    "timestamp": memory["timestamp"]
                })
                
                # Update access count
                memory["access_count"] += 1
            
            # Sort by score and return top-k
            scored_memories.sort(key=lambda x: x["score"], reverse=True)
            return scored_memories[:top_k]
            
        except Exception as e:
            logger.error(f"Semantic memory retrieval failed: {e}")
            return []
    
    async def get_user_context(self, user_id: str) -> Dict[str, Any]:
        """Get user context from long-term memory.
        
        Args:
            user_id: User identifier
            
        Returns:
            User context
        """
        if user_id not in self._user_memory:
            # Try to load from long-term memory
            if user_id in self._long_term_memory:
                self._user_memory[user_id] = self._long_term_memory[user_id]
            else:
                self._user_memory[user_id] = {}
        
        return self._user_memory[user_id]
    
    async def update_user_context(
        self,
        user_id: str,
        context: Dict[str, Any]
    ) -> None:
        """Update user context.
        
        Args:
            user_id: User identifier
            context: Context to update
        """
        if user_id not in self._user_memory:
            self._user_memory[user_id] = {}
        
        self._user_memory[user_id].update(context)
        
        # Also save to long-term memory
        self._long_term_memory[user_id] = self._user_memory[user_id].copy()
        
        logger.debug(f"Updated user context for {user_id}")
    
    async def get_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task state.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task state or None
        """
        return self._task_memory.get(task_id)
    
    async def set_task_state(
        self,
        task_id: str,
        state: Dict[str, Any]
    ) -> None:
        """Set task state.
        
        Args:
            task_id: Task identifier
            state: Task state
        """
        self._task_memory[task_id] = state
        logger.debug(f"Set task state for {task_id}")
    
    async def summarize_conversation(self, session_id: str) -> Optional[str]:
        """Summarize old conversation.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Summary or None
        """
        if session_id not in self._conversation_memory:
            return None
        
        messages = list(self._conversation_memory[session_id])
        
        if len(messages) < 10:
            return None  # Not enough messages to summarize
        
        try:
            # Use AI to summarize
            from app.services.ai import get_ai_router
            router = get_ai_router()
            
            # Build conversation text
            conversation_text = "\n".join([
                f"{m['role']}: {m['content']}"
                for m in messages[:-10]  # Summarize all but last 10
            ])
            
            summary = await router.summarize(
                conversation_text,
                max_length=200,
                use_cache=True
            )
            
            # Store summary
            self._summarized_memory[session_id] = summary
            
            # Clear old messages
            self._conversation_memory[session_id] = deque(
                messages[-10:],
                maxlen=self._max_conversation_length
            )
            
            logger.info(f"Summarized conversation for {session_id}: {summary[:80]}...")
            return summary
            
        except Exception as e:
            logger.error(f"Conversation summarization failed: {e}")
            return None
    
    async def prune_old_memories(self) -> None:
        """Prune old memories based on TTL."""
        now = datetime.utcnow()
        
        # Prune conversation memory
        for session_id in list(self._conversation_memory.keys()):
            messages = self._conversation_memory[session_id]
            if not messages:
                continue
            
            # Check oldest message
            oldest = messages[0]
            oldest_time = datetime.fromisoformat(oldest["timestamp"])
            
            if now - oldest_time > self._conversation_ttl:
                # Summarize before deleting
                await self.summarize_conversation(session_id)
                
                # If still old, delete
                if session_id in self._conversation_memory:
                    messages = self._conversation_memory[session_id]
                    if messages:
                        oldest_time = datetime.fromisoformat(messages[0]["timestamp"])
                        if now - oldest_time > self._conversation_ttl:
                            del self._conversation_memory[session_id]
        
        # Prune semantic memory
        self._semantic_memory = [
            m for m in self._semantic_memory
            if datetime.fromisoformat(m["timestamp"]) > now - self._semantic_ttl
        ]
        
        logger.info("Memory pruning complete")
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Similarity score (0-1)
        """
        import math
        
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return {
            "conversation_sessions": len(self._conversation_memory),
            "semantic_memories": len(self._semantic_memory),
            "long_term_users": len(self._long_term_memory),
            "summarized_sessions": len(self._summarized_memory),
            "active_tasks": len(self._task_memory)
        }
    
    async def clear_session(self, session_id: str) -> None:
        """Clear session memory.
        
        Args:
            session_id: Session identifier
        """
        if session_id in self._conversation_memory:
            del self._conversation_memory[session_id]
        if session_id in self._summarized_memory:
            del self._summarized_memory[session_id]
        
        logger.info(f"Cleared session memory: {session_id}")
    
    async def clear_all(self) -> None:
        """Clear all memory."""
        self._conversation_memory.clear()
        self._semantic_memory.clear()
        self._long_term_memory.clear()
        self._summarized_memory.clear()
        self._user_memory.clear()
        self._task_memory.clear()
        
        logger.info("All memory cleared")


# Singleton instance
_memory_manager = None


def get_memory_manager() -> MemoryManager:
    """Get or create singleton memory manager."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager