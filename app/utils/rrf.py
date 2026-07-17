"""Reciprocal Rank Fusion - Merge dense + sparse retrieval results.

RRF combines multiple ranked lists without score normalization.
Standard implementation used in hybrid search systems.
"""
from typing import List, Any


def reciprocal_rank_fusion(
    result_lists: List[List[Any]],
    k: int = 60
) -> List[Any]:
    """Fuse multiple ranked result lists using Reciprocal Rank Fusion.
    
    Args:
        *result_lists: Variable number of ranked result lists
        k: RRF constant (standard = 60, lower = more weight to top ranks)
        
    Returns:
        Fused and re-ranked results
    """
    scores: dict[str, float] = {}
    docs: dict[str, Any] = {}
    
    for results in result_lists:
        for rank, result in enumerate(results):
            # Use result ID as unique key
            # Handle both Qdrant points (have .id) and ScoredChunks (have .metadata)
            if hasattr(result, 'id'):
                doc_id = str(result.id)
            elif hasattr(result, 'metadata') and result.metadata:
                doc_id = str(result.metadata.get('id', result.metadata.get('document_id', '')))
            else:
                doc_id = str(rank)  # Fallback to rank if no ID found
            
            if not doc_id:
                continue  # Skip results without valid ID
            
            # RRF formula: 1 / (k + rank + 1)
            # rank is 0-indexed, so add 1
            rrf_score = 1.0 / (k + rank + 1)
            scores[doc_id] = scores.get(doc_id, 0.0) + rrf_score
            
            # Store the result object (keep highest-ranked occurrence)
            if doc_id not in docs:
                docs[doc_id] = result
    
    # Sort by RRF score descending
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    
    return [docs[doc_id] for doc_id in sorted_ids]