"""
Multi-backend storage system for conversation threads

This module provides a unified interface for conversation storage with support for:
1. File-based storage (default) - Persistent storage in ~/.zen/conversations/
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
from typing import Optional

from .storage_base import InMemoryStorage, StorageBackend

logger = logging.getLogger(__name__)


# Global singleton instance
_storage_instance: Optional[StorageBackend] = None
_storage_lock = threading.Lock()


def get_storage_backend() -> StorageBackend:
    """Get the global storage instance (singleton pattern)"""
    global _storage_instance
    if _storage_instance is None:
        with _storage_lock:
            if _storage_instance is None:
                # Check storage preference - default to file-based for CLI
                storage_type = os.getenv("ZEN_STORAGE_TYPE", "file").lower()
                logger.info(f"Storage type selected: {storage_type}")

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
                        logger.info("Initialized in-memory conversation storage (file fallback)")

                elif storage_type == "memory":
                    # In-memory storage (ephemeral)
                    _storage_instance = InMemoryStorage()
                    logger.info("Initialized in-memory conversation storage")

                else:
                    logger.warning(f"Unknown storage type '{storage_type}', using in-memory storage")
                    _storage_instance = InMemoryStorage()
                    logger.info("Initialized in-memory conversation storage (default)")

    return _storage_instance
