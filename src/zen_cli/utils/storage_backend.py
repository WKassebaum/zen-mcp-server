"""
Multi-backend storage system for conversation threads

This module provides a unified interface for conversation storage with support for:
1. File-based storage (default) - Persistent storage in ~/.zen-cli/conversations/
2. Redis storage - Distributed storage for team environments
3. In-memory storage - Ephemeral storage for testing/development

Storage Backend Selection:
Set ZEN_STORAGE_TYPE environment variable to choose backend:
- "file" (default): File-based persistence
- "redis": Redis-based distributed storage  
- "memory": In-memory storage (ephemeral)

Redis Configuration (when ZEN_STORAGE_TYPE=redis):
- REDIS_HOST: Redis server host (default: localhost)
- REDIS_PORT: Redis server port (default: 6379)
- REDIS_DB: Redis database number (default: 0)
- REDIS_PASSWORD: Redis password (if required)
- REDIS_KEY_PREFIX: Key prefix for namespacing (default: zen:)

Key Features:
- Thread-safe operations across all backends
- TTL support with automatic expiration
- Graceful fallback between storage types
- Singleton pattern for consistent state
- Drop-in compatibility between backends
"""

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class InMemoryStorage:
    """Thread-safe in-memory storage for conversation threads"""

    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()
        # Match Redis behavior: cleanup interval based on conversation timeout
        # Run cleanup at 1/10th of timeout interval (e.g., 18 mins for 3 hour timeout)
        timeout_hours = int(os.getenv("CONVERSATION_TIMEOUT_HOURS", "3"))
        self._cleanup_interval = (timeout_hours * 3600) // 10
        self._cleanup_interval = max(300, self._cleanup_interval)  # Minimum 5 minutes
        self._shutdown = False

        # Start background cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._cleanup_thread.start()

        logger.info(
            f"In-memory storage initialized with {timeout_hours}h timeout, cleanup every {self._cleanup_interval//60}m"
        )

    def set_with_ttl(self, key: str, ttl_seconds: int, value: str) -> None:
        """Store value with expiration time"""
        with self._lock:
            expires_at = time.time() + ttl_seconds
            self._store[key] = (value, expires_at)
            logger.debug(f"Stored key {key} with TTL {ttl_seconds}s")

    def get(self, key: str) -> Optional[str]:
        """Retrieve value if not expired"""
        with self._lock:
            if key in self._store:
                value, expires_at = self._store[key]
                if time.time() < expires_at:
                    logger.debug(f"Retrieved key {key}")
                    return value
                else:
                    # Clean up expired entry
                    del self._store[key]
                    logger.debug(f"Key {key} expired and removed")
        return None

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        """Redis-compatible setex method"""
        self.set_with_ttl(key, ttl_seconds, value)

    def _cleanup_worker(self):
        """Background thread that periodically cleans up expired entries"""
        while not self._shutdown:
            time.sleep(self._cleanup_interval)
            self._cleanup_expired()

    def _cleanup_expired(self):
        """Remove all expired entries"""
        with self._lock:
            current_time = time.time()
            expired_keys = [k for k, (_, exp) in self._store.items() if exp < current_time]
            for key in expired_keys:
                del self._store[key]

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired conversation threads")

    def shutdown(self):
        """Graceful shutdown of background thread"""
        self._shutdown = True
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1)


# Global singleton instance
_storage_instance = None
_storage_lock = threading.Lock()


def get_storage_backend():
    """Get the global storage instance (singleton pattern)"""
    global _storage_instance
    if _storage_instance is None:
        with _storage_lock:
            if _storage_instance is None:
                # Check storage preference - default to file-based for CLI
                storage_type = os.getenv("ZEN_STORAGE_TYPE", "file").lower()
                print(f"[DEBUG] Storage type selected: {storage_type}")
                
                if storage_type == "redis":
                    # Redis storage for distributed/team environments
                    try:
                        from .redis_storage import RedisStorage
                        _storage_instance = RedisStorage()
                        logger.info("Initialized Redis conversation storage")
                    except ImportError as e:
                        logger.warning(f"Redis storage unavailable - redis package not installed ({e})")
                        logger.warning("Install with: pip install redis")
                        logger.info("Falling back to file-based storage")
                        try:
                            from .file_storage import FileBasedStorage
                            _storage_instance = FileBasedStorage()
                            logger.info("Initialized file-based conversation storage (Redis fallback)")
                        except ImportError:
                            _storage_instance = InMemoryStorage()
                            logger.info("Initialized in-memory conversation storage (final fallback)")
                    except Exception as e:
                        logger.warning(f"Redis connection failed ({e}), falling back to file storage")
                        try:
                            from .file_storage import FileBasedStorage
                            _storage_instance = FileBasedStorage()
                            logger.info("Initialized file-based conversation storage (Redis fallback)")
                        except ImportError:
                            _storage_instance = InMemoryStorage()
                            logger.info("Initialized in-memory conversation storage (final fallback)")
                            
                elif storage_type == "file":
                    # File-based storage for CLI persistence
                    try:
                        from .file_storage import FileBasedStorage
                        _storage_instance = FileBasedStorage()
                        logger.info("Initialized file-based conversation storage")
                    except ImportError as e:
                        logger.warning(f"File storage unavailable ({e}), falling back to in-memory")
                        _storage_instance = InMemoryStorage()
                        logger.info("Initialized in-memory conversation storage (fallback)")
                        
                elif storage_type == "memory":
                    # Explicitly requested in-memory storage
                    _storage_instance = InMemoryStorage()
                    logger.info("Initialized in-memory conversation storage")
                    
                else:
                    # Unknown storage type, default to file
                    logger.warning(f"Unknown storage type '{storage_type}', defaulting to file storage")
                    try:
                        from .file_storage import FileBasedStorage
                        _storage_instance = FileBasedStorage()
                        logger.info("Initialized file-based conversation storage (default)")
                    except ImportError as e:
                        logger.warning(f"File storage unavailable ({e}), falling back to in-memory")
                        _storage_instance = InMemoryStorage()
                        logger.info("Initialized in-memory conversation storage (final fallback)")
                    
    return _storage_instance
