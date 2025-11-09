"""
Redis storage backend for conversation threads

This module provides a Redis-based storage backend for persistent conversation
contexts across distributed systems. It's designed for team environments where
multiple users need to share conversation state.

Key Features:
- Redis connection pooling and failure handling
- TTL support with automatic expiration
- Key namespacing per project/environment
- Connection retry logic and graceful degradation
- Thread-safe operations
- Drop-in replacement for FileBasedStorage

Configuration via environment variables:
- REDIS_HOST: Redis server host (default: localhost)
- REDIS_PORT: Redis server port (default: 6379)
- REDIS_DB: Redis database number (default: 0)
- REDIS_PASSWORD: Redis password (if required)
- REDIS_KEY_PREFIX: Key prefix for namespacing (default: zen:)
- REDIS_POOL_SIZE: Connection pool size (default: 10)
"""

import json
import logging
import os
import time
from typing import Any, Optional

import redis
from redis.connection import ConnectionPool

from .storage_base import StorageBackend

logger = logging.getLogger(__name__)


class RedisStorage(StorageBackend):
    """Redis-based storage for conversation threads with high availability"""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: int = None,
        password: str = None,
        key_prefix: str = None,
        pool_size: int = None,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
        max_connections: int = None,
    ):
        """
        Initialize Redis storage with connection pooling and error handling.

        Args:
            host: Redis server host
            port: Redis server port
            db: Redis database number
            password: Redis password (if required)
            key_prefix: Key prefix for namespacing
            pool_size: Connection pool size
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Socket connect timeout in seconds
            retry_on_timeout: Whether to retry on timeout
            max_connections: Maximum connections in pool
        """
        # Load configuration from environment or use defaults
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.db = db or int(os.getenv("REDIS_DB", "0"))
        self.password = password or os.getenv("REDIS_PASSWORD")
        self.key_prefix = key_prefix or os.getenv("REDIS_KEY_PREFIX", "zen:")
        self.pool_size = pool_size or int(os.getenv("REDIS_POOL_SIZE", "10"))
        self.max_connections = max_connections or self.pool_size * 2

        # Create connection pool
        try:
            self.pool = ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True,
                socket_timeout=socket_timeout,
                socket_connect_timeout=socket_connect_timeout,
                retry_on_timeout=retry_on_timeout,
                max_connections=self.max_connections,
            )

            # Initialize Redis client
            self.redis = redis.Redis(connection_pool=self.pool)

            # Test connection
            self._test_connection()

            logger.info(f"Redis storage initialized: {self.host}:{self.port}/{self.db} (prefix: {self.key_prefix})")

        except Exception as e:
            logger.error(f"Failed to initialize Redis storage: {e}")
            raise ConnectionError(f"Cannot connect to Redis at {self.host}:{self.port}: {e}")

    def _test_connection(self):
        """Test Redis connection with timeout"""
        try:
            self.redis.ping()
        except Exception as e:
            raise ConnectionError(f"Redis connection failed: {e}")

    def _get_key(self, key: str) -> str:
        """Get namespaced key with prefix"""
        return f"{self.key_prefix}{key}"

    def set(self, key: str, value: dict[str, Any], ttl: Optional[int] = None) -> None:
        """
        Store value with optional TTL (implements StorageBackend interface).

        Args:
            key: Storage key
            value: Dict value to store
            ttl: Time to live in seconds (default: 10800 = 3 hours)
        """
        ttl_seconds = ttl or 10800
        try:
            namespaced_key = self._get_key(key)

            # Serialize dict to JSON string
            json_value = json.dumps(value)

            # Store with TTL using SETEX for atomic operation
            self.redis.setex(namespaced_key, ttl_seconds, json_value)

            logger.debug(f"Stored key {key} with TTL {ttl_seconds}s in Redis")

        except redis.RedisError as e:
            logger.error(f"Redis setex failed for key {key}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Redis setex for key {key}: {e}")
            raise

    def get(self, key: str) -> Optional[dict[str, Any]]:
        """
        Retrieve value from Redis if not expired (implements StorageBackend interface).

        Args:
            key: Storage key

        Returns:
            Dict value if exists and not expired, None otherwise
        """
        try:
            namespaced_key = self._get_key(key)
            value = self.redis.get(namespaced_key)

            if value is not None:
                logger.debug(f"Retrieved key {key} from Redis")
                # Deserialize JSON string to dict
                return json.loads(value)
            else:
                logger.debug(f"Key {key} not found or expired in Redis")
                return None

        except redis.RedisError as e:
            logger.error(f"Redis get failed for key {key}: {e}")
            # Return None for Redis errors to allow graceful degradation
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Redis get for key {key}: {e}")
            return None

    def delete(self, key: str) -> None:
        """
        Delete a key from Redis.

        Args:
            key: Storage key

        Returns:
            True if key was deleted, False if key didn't exist
        """
        try:
            namespaced_key = self._get_key(key)
            result = self.redis.delete(namespaced_key)

            if result > 0:
                logger.debug(f"Deleted key {key} from Redis")
                return True
            else:
                logger.debug(f"Key {key} not found for deletion in Redis")
                return False

        except redis.RedisError as e:
            logger.error(f"Redis delete failed for key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in Redis delete for key {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        """
        Check if key exists in Redis.

        Args:
            key: Storage key

        Returns:
            True if key exists, False otherwise
        """
        try:
            namespaced_key = self._get_key(key)
            return bool(self.redis.exists(namespaced_key))
        except redis.RedisError as e:
            logger.error(f"Redis exists check failed for key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in Redis exists for key {key}: {e}")
            return False

    def list_keys(self, pattern: str = "*") -> list[str]:
        """
        List all keys matching pattern (implements StorageBackend interface).

        Args:
            pattern: Pattern to match keys against

        Returns:
            List of keys matching pattern
        """
        try:
            # Convert pattern to Redis pattern with prefix
            if pattern == "*":
                redis_pattern = f"{self.key_prefix}*"
            else:
                redis_pattern = f"{self.key_prefix}{pattern}"

            namespaced_keys = self.redis.keys(redis_pattern)

            # Remove prefix from keys
            keys = [key[len(self.key_prefix) :] for key in namespaced_keys]

            logger.debug(f"Listed {len(keys)} keys matching pattern {pattern}")
            return keys

        except redis.RedisError as e:
            logger.error(f"Redis keys listing failed for pattern {pattern}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing Redis keys for pattern {pattern}: {e}")
            return []

    def ttl(self, key: str) -> int:
        """
        Get TTL (time to live) for a key.

        Args:
            key: Storage key

        Returns:
            TTL in seconds, -1 if no expiry, -2 if key doesn't exist
        """
        try:
            namespaced_key = self._get_key(key)
            return self.redis.ttl(namespaced_key)
        except redis.RedisError as e:
            logger.error(f"Redis TTL check failed for key {key}: {e}")
            return -2
        except Exception as e:
            logger.error(f"Unexpected error in Redis TTL for key {key}: {e}")
            return -2

    def list_active_conversations(self) -> list[tuple[str, dict[str, Any]]]:
        """
        List all active conversation sessions with metadata.

        Returns:
            List of tuples: (session_id, metadata_dict)
        """
        try:
            pattern = f"{self.key_prefix}*"
            keys = self.redis.keys(pattern)

            conversations = []
            for namespaced_key in keys:
                # Remove prefix to get original key
                key = namespaced_key[len(self.key_prefix) :]

                # Skip non-conversation keys (could be used for other data)
                if not key.startswith(("conv_", "session_", "thread_")) and not key.startswith("auto_"):
                    continue

                try:
                    # Get value and TTL
                    value = self.redis.get(namespaced_key)
                    ttl_seconds = self.redis.ttl(namespaced_key)

                    if value is None:
                        continue

                    # Create metadata
                    current_time = time.time()
                    if ttl_seconds > 0:
                        expires_at = current_time + ttl_seconds
                        created_at = expires_at - (3 * 3600)  # Assume 3h default TTL
                    else:
                        expires_at = current_time + (24 * 3600)  # Default 24h if no TTL
                        created_at = current_time - 3600  # Assume created 1h ago

                    metadata = {
                        "created_at": created_at,
                        "expires_at": expires_at,
                        "ttl_seconds": ttl_seconds,
                        "size_bytes": len(value.encode("utf-8")),
                        "backend": "redis",
                        "host": f"{self.host}:{self.port}",
                        "db": self.db,
                    }

                    conversations.append((key, metadata))

                except Exception as e:
                    logger.warning(f"Error processing conversation key {key}: {e}")
                    continue

            # Sort by expiration time (most recent first)
            conversations.sort(key=lambda x: x[1]["expires_at"], reverse=True)

            logger.debug(f"Found {len(conversations)} active conversations in Redis")
            return conversations

        except redis.RedisError as e:
            logger.error(f"Redis scan failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing conversations: {e}")
            return []

    def cleanup_expired(self) -> int:
        """
        Manually cleanup expired keys (Redis handles this automatically, but this can be used for reporting).

        Returns:
            Number of expired keys found (Redis auto-expires them)
        """
        try:
            pattern = f"{self.key_prefix}*"
            keys = self.redis.keys(pattern)

            expired_count = 0
            for key in keys:
                ttl_seconds = self.redis.ttl(key)
                if ttl_seconds == -2:  # Key doesn't exist (was expired)
                    expired_count += 1

            if expired_count > 0:
                logger.info(f"Found {expired_count} expired conversation threads (auto-cleaned by Redis)")

            return expired_count

        except redis.RedisError as e:
            logger.error(f"Redis cleanup scan failed: {e}")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error in cleanup: {e}")
            return 0

    def health_check(self) -> dict[str, Any]:
        """
        Check Redis connection health and return status information.

        Returns:
            Dictionary with health status and connection info
        """
        try:
            start_time = time.time()
            info = self.redis.info()
            ping_time = time.time() - start_time

            return {
                "healthy": True,
                "backend": "redis",
                "host": f"{self.host}:{self.port}",
                "db": self.db,
                "ping_ms": round(ping_time * 1000, 2),
                "version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "total_connections_received": info.get("total_connections_received", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }

        except Exception as e:
            return {
                "healthy": False,
                "backend": "redis",
                "host": f"{self.host}:{self.port}",
                "db": self.db,
                "error": str(e),
                "ping_ms": None,
            }

    def close(self):
        """Close Redis connection pool gracefully"""
        try:
            if hasattr(self, "pool") and self.pool:
                self.pool.disconnect()
                logger.info("Redis connection pool closed")
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def get_redis_storage(**kwargs) -> RedisStorage:
    """
    Factory function to create RedisStorage instance with configuration.

    Args:
        **kwargs: Configuration parameters passed to RedisStorage constructor

    Returns:
        Configured RedisStorage instance

    Raises:
        ConnectionError: If Redis connection fails
    """
    return RedisStorage(**kwargs)


# Example configuration for different environments
REDIS_CONFIGS = {
    "local": {"host": "localhost", "port": 6379, "db": 0, "key_prefix": "zen:local:"},
    "docker": {"host": "redis", "port": 6379, "db": 0, "key_prefix": "zen:docker:"},  # Docker service name
    "production": {
        "host": "redis.example.com",
        "port": 6379,
        "db": 0,
        "password": os.getenv("REDIS_PASSWORD"),  # Required for production
        "key_prefix": "zen:prod:",
    },
}
