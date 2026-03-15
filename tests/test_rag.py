"""Tests for RAG store and retriever."""
import pytest
import tempfile
import os
from src.rag.store import seed_interests, get_collection
from src.rag.retriever import retrieve_interests, filter_articles_by_interests


@pytest.fixture
def temp_chroma_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestRAGStore:
    def test_seed_interests(self, temp_chroma_dir):
        interests = ["AI", "machine learning", "Python"]
        seed_interests(temp_chroma_dir, interests)
        collection = get_collection(temp_chroma_dir)
        assert collection.count() == 3

    def test_seed_idempotent(self, temp_chroma_dir):
        interests = ["AI", "machine learning"]
        seed_interests(temp_chroma_dir, interests)
        seed_interests(temp_chroma_dir, interests)  # Second call should not duplicate
        collection = get_collection(temp_chroma_dir)
        assert collection.count() == 2


class TestRAGRetriever:
    def test_retrieve_interests(self, temp_chroma_dir):
        interests = ["artificial intelligence", "machine learning", "Python programming"]
        seed_interests(temp_chroma_dir, interests)
        results = retrieve_interests(temp_chroma_dir, "AI and ML models", n_results=2)
        assert len(results) <= 2
        assert len(results) > 0

    def test_retrieve_empty_collection(self, temp_chroma_dir):
        results = retrieve_interests(temp_chroma_dir, "AI", n_results=3)
        assert results == []


class TestFilterArticles:
    def test_filter_by_interest(self):
        articles = [
            {"title": "New AI model released", "summary": "GPT-5 launched"},
            {"title": "Python tips for developers", "summary": "Python best practices"},
            {"title": "Cooking recipes", "summary": "How to cook pasta"},
        ]
        filtered = filter_articles_by_interests(articles, ["ai", "python"])
        titles = [a["title"].lower() for a in filtered]
        assert any("ai" in t for t in titles)
        assert any("python" in t for t in titles)
        assert not any("cooking" in t for t in titles)

    def test_filter_fallback_when_no_match(self):
        articles = [{"title": "Cooking", "summary": "pasta"}]
        filtered = filter_articles_by_interests(articles, ["AI"])
        # Fallback: return all
        assert len(filtered) == 1

    def test_filter_empty_interests_returns_all(self):
        articles = [{"title": "A", "summary": "b"}, {"title": "C", "summary": "d"}]
        filtered = filter_articles_by_interests(articles, [])
        assert filtered == articles
