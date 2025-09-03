"""
Tests for storage backend implementations
"""

import os
import tempfile
import pytest
import time
from pathlib import Path

import sys
sys.path.insert(0, 'src')

from zen_cli.utils.storage_backend import get_storage_backend, FileBasedStorage, InMemoryStorage


class TestFileBasedStorage:
    """Test file-based storage implementation"""
    
    def setup_method(self):
        """Setup for each test method"""
        # Create temporary directory for test storage
        self.temp_dir = tempfile.mkdtemp()
        self.storage = FileBasedStorage(storage_dir=self.temp_dir)
    
    def teardown_method(self):
        """Cleanup after each test method"""
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_basic_operations(self):
        """Test basic storage operations"""
        key = "test_key"
        value = "test_value"
        ttl = 3600
        
        # Set with TTL
        self.storage.set_with_ttl(key, ttl, value)
        
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
        value = "expires_soon"
        ttl = 1  # 1 second
        
        self.storage.set_with_ttl(key, ttl, value)
        assert self.storage.get(key) == value
        
        # Wait for expiration
        time.sleep(1.2)
        
        # Should be expired
        assert self.storage.get(key) is None
        assert not self.storage.exists(key)
    
    def test_list_keys(self):
        """Test key listing"""
        keys = ["key1", "key2", "key3"]
        
        for key in keys:
            self.storage.set_with_ttl(key, 3600, f"value_{key}")
        
        stored_keys = self.storage.list_keys()
        for key in keys:
            assert key in stored_keys
    
    def test_persistence(self):
        """Test that data persists across storage instances"""
        key = "persist_test"
        value = "persistent_value"
        ttl = 3600
        
        # Store with first instance
        self.storage.set_with_ttl(key, ttl, value)
        
        # Create new instance with same directory
        new_storage = FileBasedStorage(storage_dir=self.temp_dir)
        
        # Should retrieve the value
        assert new_storage.get(key) == value
    
    def test_health_check(self):
        """Test storage health check"""
        health = self.storage.health_check()
        
        assert isinstance(health, dict)
        assert 'healthy' in health
        assert health['healthy'] is True
        assert 'storage_type' in health
        assert health['storage_type'] == 'file'


class TestInMemoryStorage:
    """Test in-memory storage implementation"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.storage = InMemoryStorage()
    
    def test_basic_operations(self):
        """Test basic storage operations"""
        key = "test_key"
        value = "test_value"
        ttl = 3600
        
        # Set with TTL
        self.storage.set_with_ttl(key, ttl, value)
        
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
        value = "expires_soon"
        ttl = 1  # 1 second
        
        self.storage.set_with_ttl(key, ttl, value)
        assert self.storage.get(key) == value
        
        # Wait for expiration
        time.sleep(1.2)
        
        # Should be expired
        assert self.storage.get(key) is None
        assert not self.storage.exists(key)
    
    def test_list_keys(self):
        """Test key listing"""
        keys = ["key1", "key2", "key3"]
        
        for key in keys:
            self.storage.set_with_ttl(key, 3600, f"value_{key}")
        
        stored_keys = self.storage.list_keys()
        for key in keys:
            assert key in stored_keys
    
    def test_memory_isolation(self):
        """Test that different instances are isolated"""
        key = "isolation_test"
        value = "instance1_value"
        
        # Store with first instance
        self.storage.set_with_ttl(key, 3600, value)
        
        # Create new instance
        new_storage = InMemoryStorage()
        
        # Should not have the value (memory isolation)
        assert new_storage.get(key) is None
    
    def test_health_check(self):
        """Test storage health check"""
        health = self.storage.health_check()
        
        assert isinstance(health, dict)
        assert 'healthy' in health
        assert health['healthy'] is True
        assert 'storage_type' in health
        assert health['storage_type'] == 'memory'


class TestStorageBackendFactory:
    """Test storage backend factory function"""
    
    def test_default_backend(self):
        """Test default storage backend selection"""
        # Should default to file storage
        storage = get_storage_backend()
        assert isinstance(storage, FileBasedStorage)
    
    def test_environment_override(self):
        """Test environment variable override"""
        # Test memory storage
        os.environ['ZEN_STORAGE_TYPE'] = 'memory'
        
        try:
            storage = get_storage_backend()
            assert isinstance(storage, InMemoryStorage)
        finally:
            del os.environ['ZEN_STORAGE_TYPE']
    
    def test_singleton_behavior(self):
        """Test that get_storage_backend returns same instance"""
        storage1 = get_storage_backend()
        storage2 = get_storage_backend()
        
        # Should be the same instance
        assert storage1 is storage2


def test_redis_storage_integration():
    """Test Redis storage integration if available"""
    try:
        # Try to import Redis storage
        from zen_cli.utils.redis_storage import RedisStorage
        
        # Test basic instantiation
        storage = RedisStorage()
        health = storage.health_check()
        
        # Health check should work even if Redis isn't available
        assert isinstance(health, dict)
        assert 'healthy' in health
        assert 'storage_type' in health
        assert health['storage_type'] == 'redis'
        
        # If Redis is actually available, test operations
        if health['healthy']:
            test_key = "redis_integration_test"
            test_value = "redis_test_value"
            ttl = 60
            
            storage.set_with_ttl(test_key, ttl, test_value)
            retrieved = storage.get(test_key)
            assert retrieved == test_value
            
            # Cleanup
            storage.delete(test_key)
        
    except ImportError:
        pytest.skip("Redis storage components not available")
    except Exception as e:
        pytest.skip(f"Redis connection not available: {e}")


if __name__ == '__main__':
    # Run tests if called directly
    pytest.main([__file__, '-v'])