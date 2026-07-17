"""GPU Utilities - VRAM monitoring and management.

Monitors GPU memory usage to make intelligent routing decisions
for generation (local vs API-based).
"""
from typing import Optional
from loguru import logger


def vram_available(min_free_mb: int = 1500) -> bool:
    """Check if sufficient VRAM is available.
    
    Args:
        min_free_mb: Minimum free VRAM in MB (default 1.5GB)
        
    Returns:
        True if enough VRAM is available
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        
        free_bytes = torch.cuda.mem_get_info()[0]
        free_mb = free_bytes / (1024 * 1024)
        
        logger.debug(f"VRAM available: {free_mb:.0f}MB (need {min_free_mb}MB)")
        return free_mb >= min_free_mb
        
    except Exception as e:
        logger.warning(f"VRAM check failed: {e}")
        return False


def get_vram_info() -> dict:
    """Get detailed VRAM information.
    
    Returns:
        Dictionary with VRAM stats
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return {"available": False}
        
        total_bytes, free_bytes = torch.cuda.mem_get_info()
        total_mb = total_bytes / (1024 * 1024)
        free_mb = free_bytes / (1024 * 1024)
        used_mb = total_mb - free_mb
        
        return {
            "available": True,
            "total_mb": total_mb,
            "used_mb": used_mb,
            "free_mb": free_mb,
            "utilization_pct": (used_mb / total_mb * 100) if total_mb > 0 else 0,
        }
        
    except Exception as e:
        logger.warning(f"VRAM info failed: {e}")
        return {"available": False, "error": str(e)}


def should_use_local_generation(context_length: int = 0) -> bool:
    """Determine if local generation should be used.
    
    Args:
        context_length: Estimated context length in tokens
        
    Returns:
        True if local generation is viable
    """
    # Need at least 1.5GB free for Qwen2.5-3B
    # Add 0.5GB buffer for context overhead
    min_vram = 1500 + (context_length * 0.01)  # Rough estimate
    
    return vram_available(min_free_mb=min_vram)