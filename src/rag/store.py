"""ChromaDB vector store for user interest profiles."""
import chromadb
from chromadb.utils import embedding_functions
import structlog
from functools import lru_cache

logger = structlog.get_logger()

COLLECTION_NAME = "user_interests"


@lru_cache(maxsize=1)
def get_chroma_client(persist_dir: str) -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=persist_dir)


def get_collection(persist_dir: str) -> chromadb.Collection:
    client = get_chroma_client(persist_dir)
    ef = embedding_functions.DefaultEmbeddingFunction()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def seed_interests(persist_dir: str, interests: list[str]) -> None:
    """Populate the collection with default user interests if empty."""
    collection = get_collection(persist_dir)
    if collection.count() > 0:
        logger.info("interests_already_seeded", count=collection.count())
        return

    documents = interests
    ids = [f"interest_{i}" for i in range(len(interests))]
    collection.add(documents=documents, ids=ids)
    logger.info("interests_seeded", count=len(interests))


def upsert_interest(persist_dir: str, interest: str, interest_id: str) -> None:
    """Add or update a single interest."""
    collection = get_collection(persist_dir)
    collection.upsert(documents=[interest], ids=[interest_id])
    logger.info("interest_upserted", interest=interest, id=interest_id)
