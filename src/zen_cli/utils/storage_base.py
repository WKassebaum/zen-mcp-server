"""Base storage interface and in-memory implementation.

This module defines the storage interface and provides the in-memory implementation
to avoid circular imports between storage modules.
"""

import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StorageBackend:
    """Abstract base class for storage backends."""

    def get(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve a value from storage."""
        raise NotImplementedError

    def set(self, key: str, value: dict[str, Any], ttl: Optional[int] = None) -> None:
        """Store a value with optional TTL."""
        raise NotImplementedError

    def delete(self, key: str) -> None:
        """Delete a value from storage."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        raise NotImplementedError

    def list_keys(self, pattern: str = "*") -> list[str]:
        """List all keys matching pattern."""
        raise NotImplementedError


class InMemoryStorage(StorageBackend):
    """Thread-safe in-memory storage for conversation state."""

    def __init__(self, default_ttl: int = 10800):  # 3 hours default
        self._storage = {}
        self._lock = threading.Lock()
        self._ttl = default_ttl
        self._shutdown = False

        # Start cleanup thread for expired entries (unless in CLI mode)
        if os.getenv("ZEN_CLI_MODE") != "1":
            self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
            self._cleanup_thread.start()
        else:
            self._cleanup_thread = None

        logger.info("In-memory storage initialized with TTL: %d seconds", self._ttl)

    def _cleanup_worker(self):
        """Background thread that periodically cleans up expired entries."""
        while not self._shutdown:
            time.sleep(60)  # Check every minute
            with self._lock:
                self._cleanup_expired()

    def _cleanup_expired(self):
        """Remove all expired entries from storage (must be called with lock held)."""
        current_time = time.time()
        expired_keys = []

        for key, data in self._storage.items():
            if "expires_at" in data and current_time >= data["expires_at"]:
                expired_keys.append(key)

        for key in expired_keys:
            del self._storage[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired entries")

    def get(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve a conversation thread from storage."""
        with self._lock:
            data = self._storage.get(key)
            if data:
                # Check if expired
                if "expires_at" in data and time.time() >= data["expires_at"]:
                    del self._storage[key]
                    return None
                return data.get("value")
            return None

    def set(self, key: str, value: dict[str, Any], ttl: Optional[int] = None) -> None:
        """Store a conversation thread with expiration."""
        with self._lock:
            expires_at = time.time() + (ttl or self._ttl)
            self._storage[key] = {"value": value, "expires_at": expires_at}

    def delete(self, key: str) -> None:
        """Delete a conversation thread."""
        with self._lock:
            if key in self._storage:
                del self._storage[key]

    def exists(self, key: str) -> bool:
        """Check if a conversation thread exists."""
        with self._lock:
            if key not in self._storage:
                return False

            # Check expiration
            data = self._storage[key]
            if "expires_at" in data and time.time() >= data["expires_at"]:
                del self._storage[key]
                return False

            return True

    def list_keys(self, pattern: str = "*") -> list[str]:
        """List all conversation thread IDs."""
        with self._lock:
            # Clean up expired first
            self._cleanup_expired()

            if pattern == "*":
                return list(self._storage.keys())

            # Simple pattern matching (only supports * at end)
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                return [k for k in self._storage.keys() if k.startswith(prefix)]

            return [k for k in self._storage.keys() if k == pattern]

    def clear(self):
        """Clear all storage (for testing)."""
        with self._lock:
            self._storage.clear()

    def shutdown(self):
        """Shutdown cleanup thread."""
        self._shutdown = True
        if hasattr(self, "_cleanup_thread") and self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1)
