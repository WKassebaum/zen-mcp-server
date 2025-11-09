"""
Tests for Zen CLI storage backend implementations

Tests the multi-backend storage system (File, Redis, Memory) to ensure:
- Unified interface (get, set, delete, exists, list_keys)
- TTL support with automatic expiration
- Thread-safe operations
- Graceful fallback between backends
"""

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from zen_cli.utils.file_storage import FileBasedStorage
from zen_cli.utils.storage_backend import get_storage_backend
from zen_cli.utils.storage_base import InMemoryStorage


class TestInMemoryStorage:
    """Test in-memory storage implementation"""

    def setup_method(self):
        """Setup for each test method"""
        os.environ["ZEN_CLI_MODE"] = "1"  # Disable cleanup thread
        self.storage = InMemoryStorage()

    def test_basic_operations(self):
        """Test basic CRUD operations"""
        key = "test_key"
        value = {"data": "test_value", "count": 42}
        ttl = 3600

        # Set with TTL
        self.storage.set(key, value, ttl=ttl)

        # Get value
        retrieved = self.storage.get(key)
        assert retrieved == value

        # Check exists
        assert self.storage.exists(key)

        # Delete
        self.storage.delete(key)
        assert not self.storage.exists(key)
        assert self.storage.get(key) is None

    def test_ttl_expiration(self):
        """Test TTL expiration"""
        key = "ttl_test"
        value = {"expires": "soon"}
        ttl = 1  # 1 second

        self.storage.set(key, value, ttl=ttl)
        assert self.storage.get(key) == value

        # Wait for expiration
        time.sleep(1.2)

        # Should be expired
        assert self.storage.get(key) is None
        assert not self.storage.exists(key)

    def test_list_keys(self):
        """Test key listing"""
        keys = ["key1", "key2", "key3"]

        for k in keys:
            self.storage.set(k, {"value": f"data_{k}"}, ttl=3600)

        stored_keys = self.storage.list_keys()
        for k in keys:
            assert k in stored_keys

    def test_list_keys_pattern(self):
        """Test key listing with pattern"""
        # Create keys with different prefixes
        self.storage.set("user:1", {"name": "Alice"}, ttl=3600)
        self.storage.set("user:2", {"name": "Bob"}, ttl=3600)
        self.storage.set("config:timeout", {"value": 30}, ttl=3600)

        # List all user keys
        user_keys = self.storage.list_keys("user:*")
        assert len(user_keys) == 2
        assert "user:1" in user_keys
        assert "user:2" in user_keys
        assert "config:timeout" not in user_keys

    def test_default_ttl(self):
        """Test default TTL when not specified"""
        key = "default_ttl_test"
        value = {"data": "test"}

        # Set without TTL (should use default)
        self.storage.set(key, value)

        # Should still exist (default is 3 hours)
        assert self.storage.exists(key)
        assert self.storage.get(key) == value

    def test_memory_isolation(self):
        """Test that different instances are isolated"""
        key = "isolation_test"
        value = {"instance": "first"}

        # Store with first instance
        self.storage.set(key, value, ttl=3600)

        # Create new instance
        new_storage = InMemoryStorage()

        # Should not have the value (memory isolation)
        assert new_storage.get(key) is None


class TestFileBasedStorage:
    """Test file-based storage implementation"""

    def setup_method(self):
        """Setup for each test method"""
        os.environ["ZEN_CLI_MODE"] = "1"  # Disable cleanup thread
        # Create temporary directory for test storage
        self.temp_dir = tempfile.mkdtemp()
        self.storage = FileBasedStorage(storage_dir=self.temp_dir)

    def teardown_method(self):
        """Cleanup after each test method"""
        # Shutdown storage
        self.storage.shutdown()
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_basic_operations(self):
        """Test basic CRUD operations"""
        key = "test_key"
        value = {"data": "test_value", "count": 42}
        ttl = 3600

        # Set with TTL
        self.storage.set(key, value, ttl=ttl)

        # Get value
        retrieved = self.storage.get(key)
        assert retrieved == value

        # Check exists
        assert self.storage.exists(key)

        # Delete
        self.storage.delete(key)
        assert not self.storage.exists(key)
        assert self.storage.get(key) is None

    def test_ttl_expiration(self):
        """Test TTL expiration"""
        key = "ttl_test"
        value = {"expires": "soon"}
        ttl = 1  # 1 second

        self.storage.set(key, value, ttl=ttl)
        assert self.storage.get(key) == value

        # Wait for expiration
        time.sleep(1.2)

        # Should be expired
        assert self.storage.get(key) is None
        assert not self.storage.exists(key)

    def test_list_keys(self):
        """Test key listing"""
        keys = ["key1", "key2", "key3"]

        for k in keys:
            self.storage.set(k, {"value": f"data_{k}"}, ttl=3600)

        stored_keys = self.storage.list_keys()
        for k in keys:
            assert k in stored_keys

    def test_persistence(self):
        """Test that data persists across storage instances"""
        key = "persist_test"
        value = {"persistent": "value"}
        ttl = 3600

        # Store with first instance
        self.storage.set(key, value, ttl=ttl)

        # Create new instance with same directory
        new_storage = FileBasedStorage(storage_dir=self.temp_dir)

        # Should retrieve the value
        assert new_storage.get(key) == value

        # Cleanup new instance
        new_storage.shutdown()

    def test_file_creation(self):
        """Test that files are created correctly"""
        key = "file_test"
        value = {"data": "file_data"}

        self.storage.set(key, value, ttl=3600)

        # Check that file exists
        conversations_dir = Path(self.temp_dir) / "conversations"
        file_path = conversations_dir / f"{key}.json"
        assert file_path.exists()

        # Cleanup
        self.storage.delete(key)
        assert not file_path.exists()

    def test_corrupted_file_handling(self):
        """Test handling of corrupted JSON files"""
        key = "corrupted_test"

        # Create corrupted file directly
        conversations_dir = Path(self.temp_dir) / "conversations"
        file_path = conversations_dir / f"{key}.json"

        with open(file_path, "w") as f:
            f.write("{ this is not valid json }")

        # Should handle corrupted file gracefully
        assert self.storage.get(key) is None
        assert not self.storage.exists(key)


class TestStorageBackendFactory:
    """Test storage backend factory function"""

    def setup_method(self):
        """Setup for each test"""
        os.environ["ZEN_CLI_MODE"] = "1"
        # Reset singleton
        import zen_cli.utils.storage_backend as sb

        sb._storage_instance = None

    def teardown_method(self):
        """Cleanup after each test"""
        # Reset singleton
        import zen_cli.utils.storage_backend as sb

        sb._storage_instance = None
        # Remove environment variables
        for key in ["ZEN_STORAGE_TYPE"]:
            if key in os.environ:
                del os.environ[key]

    def test_default_backend(self):
        """Test default storage backend selection"""
        storage = get_storage_backend()
        # Should default to file storage
        assert isinstance(storage, FileBasedStorage)

    def test_file_backend(self):
        """Test explicit file storage selection"""
        os.environ["ZEN_STORAGE_TYPE"] = "file"

        # Reset singleton
        import zen_cli.utils.storage_backend as sb

        sb._storage_instance = None

        storage = get_storage_backend()
        assert isinstance(storage, FileBasedStorage)

    def test_memory_backend(self):
        """Test memory storage selection"""
        os.environ["ZEN_STORAGE_TYPE"] = "memory"

        # Reset singleton
        import zen_cli.utils.storage_backend as sb

        sb._storage_instance = None

        storage = get_storage_backend()
        assert isinstance(storage, InMemoryStorage)

    def test_singleton_behavior(self):
        """Test that get_storage_backend returns same instance"""
        storage1 = get_storage_backend()
        storage2 = get_storage_backend()

        # Should be the same instance
        assert storage1 is storage2

    def test_fallback_on_unknown_type(self):
        """Test fallback to in-memory on unknown storage type"""
        os.environ["ZEN_STORAGE_TYPE"] = "unknown"

        # Reset singleton
        import zen_cli.utils.storage_backend as sb

        sb._storage_instance = None

        storage = get_storage_backend()
        # Should fall back to in-memory
        assert isinstance(storage, InMemoryStorage)


class TestRedisStorage:
    """Test Redis storage implementation (if Redis is available)"""

    def setup_method(self):
        """Setup for each test"""
        try:
            from zen_cli.utils.redis_storage import RedisStorage

            self.redis_available = True
            # Try to create Redis storage
            self.storage = RedisStorage()
        except (ImportError, Exception) as e:
            self.redis_available = False
            pytest.skip(f"Redis not available: {e}")

    def teardown_method(self):
        """Cleanup after each test"""
        if self.redis_available and hasattr(self, "storage"):
            # Clean up test keys
            try:
                keys = self.storage.list_keys("test_*")
                for key in keys:
                    self.storage.delete(key)
            except:
                pass

    def test_basic_operations(self):
        """Test basic CRUD operations"""
        if not self.redis_available:
            pytest.skip("Redis not available")

        key = "test_redis_key"
        value = {"data": "redis_value", "count": 42}
        ttl = 3600

        # Set with TTL
        self.storage.set(key, value, ttl=ttl)

        # Get value
        retrieved = self.storage.get(key)
        assert retrieved == value

        # Check exists
        assert self.storage.exists(key)

        # Delete
        self.storage.delete(key)
        assert not self.storage.exists(key)

    def test_key_prefix(self):
        """Test that keys are namespaced with prefix"""
        if not self.redis_available:
            pytest.skip("Redis not available")

        key = "test_prefix"
        value = {"namespaced": True}

        self.storage.set(key, value, ttl=3600)

        # Direct Redis access should have the prefix
        namespaced_key = self.storage._get_key(key)
        assert namespaced_key.startswith(self.storage.key_prefix)

        # Cleanup
        self.storage.delete(key)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
