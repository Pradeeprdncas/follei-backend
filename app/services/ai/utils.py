"""AI Service Utilities - Shared utilities for AI operations.

This module provides:
- Text processing utilities
- Token counting
- Prompt templates
- Response formatting
"""
from typing import List, Dict, Any
import re
from loguru import logger


def count_tokens_approx(text: str) -> int:
    """Approximate token count for text.
    
    Uses simple heuristic: ~4 characters per token for English text.
    
    Args:
        text: Input text
        
    Returns:
        Approximate token count
    """
    return len(text) // 4


def truncate_text(text: str, max_tokens: int) -> str:
    """Truncate text to maximum token count.
    
    Args:
        text: Input text
        max_tokens: Maximum token count
        
    Returns:
        Truncated text
    """
    approx_chars = max_tokens * 4
    if len(text) <= approx_chars:
        return text
    
    truncated = text[:approx_chars]
    # Try to truncate at sentence boundary
    last_period = truncated.rfind('.')
    if last_period > approx_chars * 0.8:  # If we found a period in last 20%
        truncated = truncated[:last_period + 1]
    
    return truncated


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks.
    
    Args:
        text: Input text
        chunk_size: Maximum chunk size in characters
        overlap: Overlap between chunks in characters
        
    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence end in last 20% of chunk
            search_start = start + int(chunk_size * 0.8)
            sentence_end = max(
                text.rfind('. ', search_start, end),
                text.rfind('! ', search_start, end),
                text.rfind('? ', search_start, end),
            )
            
            if sentence_end > start:
                end = sentence_end + 1
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start position with overlap
        start = end - overlap
    
    return chunks


def extract_json_from_response(response: str) -> Dict[str, Any]:
    """Extract JSON from LLM response.
    
    Handles cases where LLM wraps JSON in markdown code blocks.
    
    Args:
        response: LLM response text
        
    Returns:
        Parsed JSON dictionary
    """
    import json
    
    # Try to find JSON in markdown code block
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON object directly
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Return empty dict if no JSON found
    logger.warning("No valid JSON found in response")
    return {}


def format_retrieval_context(chunks: List[Dict[str, Any]], max_length: int = 4000) -> str:
    """Format retrieved chunks into context string.
    
    Args:
        chunks: List of chunk dictionaries with 'text' and 'metadata'
        max_length: Maximum context length in characters
        
    Returns:
        Formatted context string
    """
    context_parts = []
    current_length = 0
    
    for i, chunk in enumerate(chunks, 1):
        chunk_text = chunk.get('text', '')
        metadata = chunk.get('metadata', {})
        
        # Format chunk with metadata
        source = metadata.get('source', 'Unknown')
        page = metadata.get('page', '')
        page_info = f" (Page {page})" if page else ""
        
        chunk_formatted = f"[Source {i}: {source}{page_info}]\n{chunk_text}\n"
        
        # Check if adding this chunk would exceed max length
        if current_length + len(chunk_formatted) > max_length:
            logger.warning(f"Context truncated at {max_length} characters")
            break
        
        context_parts.append(chunk_formatted)
        current_length += len(chunk_formatted)
    
    return "\n".join(context_parts)


def normalize_text(text: str) -> str:
    """Normalize text for comparison.
    
    - Lowercase
    - Remove extra whitespace
    - Remove special characters
    
    Args:
        text: Input text
        
    Returns:
        Normalized text
    """
    # Lowercase
    text = text.lower()
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Remove special characters (keep alphanumeric, spaces, basic punctuation)
    text = re.sub(r'[^a-z0-9\s.,!?\'"-]', '', text)
    
    return text.strip()


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate simple text similarity (Jaccard similarity).
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    words1 = set(normalize_text(text1).split())
    words2 = set(normalize_text(text2).split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1 & words2
    union = words1 | words2
    
    return len(intersection) / len(union)


def batch_process(items: List[Any], batch_size: int, process_func):
    """Process items in batches.
    
    Args:
        items: List of items to process
        batch_size: Number of items per batch
        process_func: Async function to process each batch
        
    Returns:
        List of results
    """
    import asyncio
    
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        result = asyncio.run(process_func(batch))
        if isinstance(result, list):
            results.extend(result)
        else:
            results.append(result)
    
    return results


def sanitize_prompt(prompt: str) -> str:
    """Sanitize prompt to prevent injection attacks.
    
    Args:
        prompt: Input prompt
        
    Returns:
        Sanitized prompt
    """
    # Remove potential injection patterns
    dangerous_patterns = [
        r'ignore\s+previous\s+instructions',
        r'disregard\s+all\s+previous',
        r'you\s+are\s+now',
        r'new\s+instructions',
        r'system\s+override',
    ]
    
    sanitized = prompt
    for pattern in dangerous_patterns:
        sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
    
    return sanitized.strip()


def format_error_response(error: Exception, context: str = "") -> Dict[str, Any]:
    """Format error into standardized response.
    
    Args:
        error: Exception object
        context: Additional context
        
    Returns:
        Formatted error response
    """
    return {
        "error": True,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context,
        "suggestion": "Please try again or contact support if the issue persists."
    }