"""
Caching subsystem for tool executions.
Reduces network roundtrips, limits API cost, and speeds up repeated queries.
"""

import hashlib
import json
import time
from typing import Any, Dict, Optional


class ToolCache:
    """In-memory cache with time-to-live (TTL) expiration support."""

    def __init__(self, default_ttl_seconds: int = 3600, enabled: bool = True):
        self.default_ttl = default_ttl_seconds
        self.enabled = enabled
        self._store: Dict[str, Dict[str, Any]] = {}

    def _make_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Computes a deterministic hash key from tool name and arguments."""
        serialized = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Any]:
        """Retrieves cached result if not expired."""
        if not self.enabled:
            return None

        key = self._make_key(tool_name, arguments)
        entry = self._store.get(key)
        if not entry:
            return None

        # Check expiration
        if time.time() > entry["expires_at"]:
            del self._store[key]
            return None

        return entry["data"]

    def set(self, tool_name: str, arguments: Dict[str, Any], data: Any, ttl_seconds: Optional[int] = None) -> None:
        """Stores tool execution result in cache with expiration."""
        if not self.enabled:
            return

        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        key = self._make_key(tool_name, arguments)
        self._store[key] = {
            "data": data,
            "cached_at": time.time(),
            "expires_at": time.time() + ttl,
        }

    def clear(self) -> None:
        """Flushes the cache."""
        self._store.clear()

    def size(self) -> int:
        """Returns number of active cache entries."""
        return len(self._store)
