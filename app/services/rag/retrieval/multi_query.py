from app.services.rag.llm.query_expander import expand_query

async def generate_queries(query: str) -> list[str]:
    try:
        variants = await expand_query(query)

        if isinstance(variants, list):
            return [query] + variants

        return [query]

    except Exception:
        return [query]