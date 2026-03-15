"""RAG retrieval — find user interests relevant to fetched articles."""
import structlog
from src.rag.store import get_collection

logger = structlog.get_logger()


def retrieve_interests(persist_dir: str, query: str, n_results: int = 3) -> list[str]:
    """Return top-N user interests most similar to the query text."""
    collection = get_collection(persist_dir)
    if collection.count() == 0:
        logger.warning("empty_interests_collection")
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
    )
    interests = results["documents"][0] if results["documents"] else []
    logger.info("interests_retrieved", query=query[:50], count=len(interests))
    return interests


def filter_articles_by_interests(
    articles: list[dict],
    interests: list[str],
) -> list[dict]:
    """Keep articles whose title/summary contains at least one interest keyword."""
    if not interests:
        return articles

    interest_lower = [i.lower() for i in interests]
    filtered = []
    for article in articles:
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        if any(interest in text for interest in interest_lower):
            filtered.append(article)

    if not filtered:
        # Fallback: return all articles if none matched
        logger.info("no_articles_matched_interests_returning_all", total=len(articles))
        return articles

    logger.info("articles_filtered", total=len(articles), matched=len(filtered))
    return filtered
