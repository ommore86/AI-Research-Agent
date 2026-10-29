"""
Unit tests for agent tools, caching, timeouts, and failure resilience.
"""

from agent.tools.cache import ToolCache
from agent.tools.registry import ToolRegistry, create_default_registry
from agent.tools.search import WebSearchTool
from agent.tools.scraper import WebScraperTool
from agent.tools.wikipedia import WikipediaTool


def test_tool_cache_set_and_get():
    cache = ToolCache(default_ttl_seconds=60, enabled=True)
    cache.set("test_tool", {"q": "python"}, {"result": "success"})

    cached = cache.get("test_tool", {"q": "python"})
    assert cached == {"result": "success"}

    # Different arguments should return None
    assert cache.get("test_tool", {"q": "java"}) is None


def test_web_search_tool_curated_fallback():
    search_tool = WebSearchTool()
    # Query matching curated index
    results = search_tool.run("vector database", max_results=3)
    assert isinstance(results, list)
    assert len(results) > 0
    assert "title" in results[0]
    assert "url" in results[0]
    assert "snippet" in results[0]


def test_web_scraper_tool_offline_cache():
    scraper = WebScraperTool()
    res = scraper.run("https://qdrant.tech", max_chars=500)
    assert res["status"] in ("success", "success (cached)")
    assert "Qdrant" in res["title"]
    assert len(res["content"]) <= 500


def test_web_scraper_tool_invalid_url():
    scraper = WebScraperTool()
    res = scraper.run("not-a-valid-url")
    assert res["status"] == "error"
    assert res["length"] == 0


def test_tool_registry_execution_and_caching():
    registry = create_default_registry(cache_enabled=True)
    assert "web_search" in registry.list_tools()
    assert "web_scraper" in registry.list_tools()
    assert "wikipedia_lookup" in registry.list_tools()

    # First call live
    res1 = registry.execute_tool("web_search", {"query": "vector database", "max_results": 2})
    assert res1.success is True
    assert res1.cached is False

    # Second call should be retrieved from cache
    res2 = registry.execute_tool("web_search", {"query": "vector database", "max_results": 2})
    assert res2.success is True
    assert res2.cached is True


def test_unregistered_tool_fails_gracefully():
    registry = create_default_registry()
    res = registry.execute_tool("non_existent_tool", {"param": 123})
    assert res.success is False
    assert "not registered" in res.error_message
