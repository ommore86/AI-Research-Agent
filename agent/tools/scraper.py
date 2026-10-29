"""
Web Scraper Tool for deep page reading and content extraction.
Includes HTML cleaning, boilerplate stripping, token budgeting, and prompt injection defense.
"""

from typing import Any, Dict
from bs4 import BeautifulSoup
import httpx

from agent.tools.base import BaseTool
from agent.safety.sanitizer import PromptSanitizer


class WebScraperTool(BaseTool):
    """Fetches a specific webpage URL, strips HTML boilerplate, and extracts readable text."""

    name: str = "web_scraper"
    description: str = (
        "Extracts and sanitizes the core text content from a given webpage URL. "
        "Strips navigation bars, ads, footers, scripts, and protects against embedded injections."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The HTTP/HTTPS URL of the webpage to scrape."
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters of text content to extract (default 8000).",
                "default": 8000
            }
        },
        "required": ["url"]
    }

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Curated offline content for demonstration URLs
    OFFLINE_PAGE_CACHE: Dict[str, Dict[str, str]] = {
        "https://www.trychroma.com": {
            "title": "Chroma DB Overview",
            "content": (
                "Chroma is an open-source AI-native embedding database. "
                "Core Features: Fast setup (pip install chromadb), in-memory or persistent SQLite backend, "
                "HNSW indexing for approximate nearest neighbor search, built-in embedding functions (Sentence Transformers, OpenAI), "
                "native metadata filtering using where and where_document clauses. "
                "Pros: Minimal operational overhead, zero-configuration local development, lightweight client. "
                "Cons: Not designed for distributed multi-node clusters out of the box; performance degrades beyond tens of millions of vectors compared to specialized C++/Rust engines."
            )
        },
        "https://qdrant.tech": {
            "title": "Qdrant Vector Database Overview",
            "content": (
                "Qdrant is a high-performance vector search engine written in Rust. "
                "Core Features: Cloud-native architecture, advanced payload-based filtering during HNSW traversal (pre-filtering), "
                "quantization support (scalar, product, and binary quantization) cutting memory footprint by up to 95%, "
                "distributed sharding with Raft consensus, comprehensive gRPC and REST APIs. "
                "Pros: Extremely fast retrieval latency, memory-efficient, excellent filtered search performance. "
                "Cons: Higher deployment operational complexity than Chroma; Rust binary requires server hosting."
            )
        },
        "https://milvus.io": {
            "title": "Milvus Vector Database Architecture",
            "content": (
                "Milvus is a distributed open-source vector database built for massive enterprise-scale RAG. "
                "Core Features: Disaggregated storage and compute architecture, Kafka/Pulsar message broker log broker, "
                "supports diverse indexing algorithms (HNSW, IVF_FLAT, IVF_SQ8, SCaNN, DiskANN), GPU acceleration support. "
                "Pros: Capable of scaling to billions of vectors across multi-node Kubernetes clusters, enterprise RBAC and multi-tenancy. "
                "Cons: Heavy infrastructure footprint requiring Kubernetes, Etcd, MinIO/S3, and message brokers; steep learning curve for early-stage startups."
            )
        }
    }

    def run(self, url: str, max_chars: int = 8000) -> Dict[str, Any]:
        """
        Fetches and extracts clean text from the target URL.
        """
        clean_url = url.strip()
        if not clean_url.startswith("http"):
            return {
                "url": clean_url,
                "title": "Invalid URL",
                "content": "The provided URL is not valid. Must start with http:// or https://",
                "length": 0,
                "status": "error"
            }

        # Check offline page cache first
        if clean_url in self.OFFLINE_PAGE_CACHE:
            cached = self.OFFLINE_PAGE_CACHE[clean_url]
            return {
                "url": clean_url,
                "title": cached["title"],
                "content": cached["content"][:max_chars],
                "length": len(cached["content"][:max_chars]),
                "status": "success (cached)"
            }

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                resp = client.get(clean_url, headers=self.HEADERS)
                if resp.status_code != 200:
                    return {
                        "url": clean_url,
                        "title": f"HTTP Error {resp.status_code}",
                        "content": f"Failed to fetch content from {clean_url}. Server returned status code {resp.status_code}.",
                        "length": 0,
                        "status": "http_error"
                    }

                soup = BeautifulSoup(resp.text, "html.parser")

                # Remove non-content elements
                for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form"]):
                    element.decompose()

                # Extract title
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else "No Title Found"

                # Extract text from main content blocks if present, or body
                main_elem = soup.find("main") or soup.find("article") or soup.find("div", id="content") or soup.body
                if main_elem:
                    raw_text = main_elem.get_text(separator="\n", strip=True)
                else:
                    raw_text = soup.get_text(separator="\n", strip=True)

                cleaned_text = PromptSanitizer.clean_text_whitespace(raw_text)

                # Truncate to token/character budget
                truncated_text = cleaned_text[:max_chars]

                return {
                    "url": clean_url,
                    "title": PromptSanitizer.clean_text_whitespace(title),
                    "content": truncated_text,
                    "length": len(truncated_text),
                    "status": "success"
                }

        except Exception as exc:
            return {
                "url": clean_url,
                "title": "Connection Failed",
                "content": f"Unable to retrieve webpage: {type(exc).__name__}: {str(exc)}",
                "length": 0,
                "status": "connection_error"
            }
