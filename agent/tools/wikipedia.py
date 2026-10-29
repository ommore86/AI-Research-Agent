"""
Wikipedia Tool for authoritative encyclopedia lookups, definitions, and technical overviews.
"""

from typing import Any, Dict
import httpx

from agent.tools.base import BaseTool
from agent.safety.sanitizer import PromptSanitizer


class WikipediaTool(BaseTool):
    """Retrieves factual summaries and definitions from Wikipedia via the MediaWiki API."""

    name: str = "wikipedia_lookup"
    description: str = (
        "Looks up authoritative technical summaries, architectural definitions, "
        "and overviews from Wikipedia. Best for established concepts, algorithms, and history."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The topic, algorithm, or concept name to look up."
            }
        },
        "required": ["query"]
    }

    HEADERS = {
        "User-Agent": "AIResearchAgent/1.0 (production-evaluation-bot@intern-assignment.org)"
    }

    def run(self, query: str) -> Dict[str, Any]:
        """
        Executes Wikipedia search and extracts the top lead summary.
        """
        clean_query = query.strip()
        if not clean_query:
            return {"title": "", "summary": "", "url": "", "status": "empty_query"}

        # Step 1: Search for page title
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "opensearch",
            "search": clean_query,
            "limit": 1,
            "namespace": 0,
            "format": "json"
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(search_url, params=search_params, headers=self.HEADERS)
                if resp.status_code != 200:
                    return {"title": clean_query, "summary": "Wikipedia API error", "url": "", "status": "api_error"}

                data = resp.json()
                titles = data[1] if len(data) > 1 else []
                urls = data[3] if len(data) > 3 else []

                if not titles:
                    return {
                        "title": clean_query,
                        "summary": f"No Wikipedia article found matching '{clean_query}'.",
                        "url": "",
                        "status": "not_found"
                    }

                matched_title = titles[0]
                matched_url = urls[0] if urls else ""

                # Step 2: Fetch page extract
                extract_params = {
                    "action": "query",
                    "prop": "extracts",
                    "exintro": True,
                    "explaintext": True,
                    "titles": matched_title,
                    "format": "json"
                }

                extract_resp = client.get(search_url, params=extract_params, headers=self.HEADERS)
                if extract_resp.status_code == 200:
                    pages = extract_resp.json().get("query", {}).get("pages", {})
                    for page_id, page_data in pages.items():
                        extract = page_data.get("extract", "")
                        return {
                            "title": matched_title,
                            "summary": PromptSanitizer.clean_text_whitespace(extract),
                            "url": matched_url,
                            "status": "success"
                        }

                return {
                    "title": matched_title,
                    "summary": f"Found page for '{matched_title}'.",
                    "url": matched_url,
                    "status": "success"
                }

        except Exception as exc:
            return {
                "title": clean_query,
                "summary": f"Wikipedia query error: {type(exc).__name__}: {str(exc)}",
                "url": "",
                "status": "error"
            }
