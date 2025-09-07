"""
Unit tests for FileCache implementation with LRU eviction

This module tests the file-based cache with LRU eviction policy to ensure
correct functionality including storage, retrieval, eviction, and statistics.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.zen_cli.utils.file_cache import FileCache, FileCacheEntry, get_file_cache, clear_file_cache


class TestFileCache(unittest.TestCase):
    """Test cases for FileCache class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for cache
        self.temp_dir = tempfile.mkdtemp()
        self.cache = FileCache(
            cache_dir=self.temp_dir,
            max_size_mb=1,  # 1MB for testing
            ttl_seconds=10,
            eviction_ratio=0.3
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        # Clear cache and remove temp directory
        self.cache.clear()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_cache_initialization(self):
        """Test cache initialization and directory creation."""
        self.assertTrue(Path(self.temp_dir).exists())
        self.assertTrue((Path(self.temp_dir) / "data").exists())
        self.assertTrue((Path(self.temp_dir) / "metadata").exists())
        
        stats = self.cache.get_stats()
        self.assertEqual(stats["file_count"], 0)
        self.assertEqual(stats["current_size_mb"], 0.0)
        self.assertEqual(stats["max_size_mb"], 1.0)
    
    def test_set_and_get(self):
        """Test basic cache set and get operations."""
        key = "test_key"
        content = "Test content for caching"
        
        # Set cache entry
        result = self.cache.set(key, content)
        self.assertTrue(result)
        
        # Get cache entry
        retrieved = self.cache.get(key)
        self.assertEqual(retrieved, content)
        
        # Check statistics
        stats = self.cache.get_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 0)
        self.assertEqual(stats["file_count"], 1)
    
    def test_cache_miss(self):
        """Test cache miss for non-existent key."""
        result = self.cache.get("non_existent_key")
        self.assertIsNone(result)
        
        stats = self.cache.get_stats()
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 1)
    
    def test_ttl_expiration(self):
        """Test TTL expiration of cache entries."""
        key = "expiring_key"
        content = "Expiring content"
        
        # Set with short TTL
        self.cache.set(key, content, ttl=1)
        
        # Should exist immediately
        self.assertEqual(self.cache.get(key), content)
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Should be expired
        result = self.cache.get(key)
        self.assertIsNone(result)
        
        # File should be removed
        data_file = self.cache.data_dir / f"{key}.cache"
        meta_file = self.cache.meta_dir / f"{key}.meta"
        self.assertFalse(data_file.exists())
        self.assertFalse(meta_file.exists())
    
    def test_lru_eviction(self):
        """Test LRU eviction when cache size limit is exceeded."""
        # Create content that's about 300KB each
        large_content = "x" * (300 * 1024)
        
        # Add first entry
        self.cache.set("key1", large_content)
        stats = self.cache.get_stats()
        self.assertEqual(stats["file_count"], 1)
        
        # Add second entry
        self.cache.set("key2", large_content)
        stats = self.cache.get_stats()
        self.assertEqual(stats["file_count"], 2)
        
        # Access key2 to make it more recently used
        self.cache.get("key2")
        
        # Add third entry - should trigger eviction of key1
        self.cache.set("key3", large_content)
        
        # key1 should be evicted (least recently used)
        self.assertIsNone(self.cache.get("key1"))
        self.assertIsNotNone(self.cache.get("key2"))
        self.assertIsNotNone(self.cache.get("key3"))
        
        stats = self.cache.get_stats()
        self.assertGreater(stats["evictions"], 0)
    
    def test_metadata_storage(self):
        """Test metadata storage with cache entries."""
        key = "meta_key"
        content = "Content with metadata"
        metadata = {"user": "test", "source": "api"}
        
        # Set with metadata
        self.cache.set(key, content, metadata=metadata)
        
        # Check metadata file
        meta_file = self.cache.meta_dir / f"{key}.meta"
        self.assertTrue(meta_file.exists())
        
        with open(meta_file, 'r') as f:
            stored_meta = json.load(f)
        
        self.assertEqual(stored_meta["key"], key)
        self.assertEqual(stored_meta["metadata"], metadata)
        self.assertIn("created_at", stored_meta)
        self.assertIn("expires_at", stored_meta)
        self.assertIn("size_bytes", stored_meta)
    
    def test_access_count_update(self):
        """Test that access count is updated on cache hits."""
        key = "access_key"
        content = "Content for access counting"
        
        self.cache.set(key, content)
        
        # Access multiple times
        for _ in range(3):
            self.cache.get(key)
        
        # Check metadata
        meta_file = self.cache.meta_dir / f"{key}.meta"
        with open(meta_file, 'r') as f:
            meta = json.load(f)
        
        self.assertEqual(meta["access_count"], 3)
    
    def test_clear_cache(self):
        """Test clearing all cache entries."""
        # Add multiple entries
        for i in range(5):
            self.cache.set(f"key{i}", f"content{i}")
        
        stats = self.cache.get_stats()
        self.assertEqual(stats["file_count"], 5)
        
        # Clear cache
        count = self.cache.clear()
        self.assertEqual(count, 5)
        
        # Verify all cleared
        stats = self.cache.get_stats()
        self.assertEqual(stats["file_count"], 0)
        self.assertEqual(stats["current_size_mb"], 0.0)
        
        # Verify files are gone
        data_files = list(self.cache.data_dir.glob("*.cache"))
        meta_files = list(self.cache.meta_dir.glob("*.meta"))
        self.assertEqual(len(data_files), 0)
        self.assertEqual(len(meta_files), 0)
    
    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        # Add entries with different TTLs
        self.cache.set("short_ttl", "content1", ttl=1)
        self.cache.set("long_ttl", "content2", ttl=100)
        
        # Wait for short TTL to expire
        time.sleep(1.5)
        
        # Run cleanup
        removed = self.cache.cleanup_expired()
        self.assertEqual(removed, 1)
        
        # Verify only long TTL entry remains
        self.assertIsNone(self.cache.get("short_ttl"))
        self.assertIsNotNone(self.cache.get("long_ttl"))
    
    def test_cache_key_generation(self):
        """Test cache key generation using SHA-256."""
        content1 = "Test content 1"
        content2 = "Test content 2"
        
        key1 = self.cache._generate_cache_key(content1)
        key2 = self.cache._generate_cache_key(content2)
        
        # Keys should be different for different content
        self.assertNotEqual(key1, key2)
        
        # Same content should generate same key
        key1_duplicate = self.cache._generate_cache_key(content1)
        self.assertEqual(key1, key1_duplicate)
        
        # Keys should be 64 characters (SHA-256 hex)
        self.assertEqual(len(key1), 64)
        self.assertEqual(len(key2), 64)
    
    def test_atomic_file_operations(self):
        """Test atomic file operations prevent corruption."""
        key = "atomic_key"
        content = "Atomic content"
        
        # Simulate failure during write by patching replace
        with patch.object(Path, 'replace', side_effect=IOError("Simulated failure")):
            result = self.cache.set(key, content)
            self.assertFalse(result)
        
        # Cache entry should not exist
        self.assertIsNone(self.cache.get(key))
        
        # No partial files should remain
        data_file = self.cache.data_dir / f"{key}.cache"
        meta_file = self.cache.meta_dir / f"{key}.meta"
        temp_files = list(self.cache.data_dir.glob("*.tmp"))
        
        self.assertFalse(data_file.exists())
        self.assertFalse(meta_file.exists())
        self.assertEqual(len(temp_files), 0)
    
    def test_corrupted_metadata_handling(self):
        """Test handling of corrupted metadata files."""
        key = "corrupted_key"
        content = "Content with corrupted metadata"
        
        # Set valid entry
        self.cache.set(key, content)
        
        # Corrupt the metadata file
        meta_file = self.cache.meta_dir / f"{key}.meta"
        with open(meta_file, 'w') as f:
            f.write("{ invalid json }")
        
        # Should handle corruption gracefully
        result = self.cache.get(key)
        self.assertIsNone(result)
        
        # Corrupted files should be removed
        self.assertFalse(meta_file.exists())
    
    def test_rebuild_cache_index(self):
        """Test cache index rebuilding on initialization."""
        # Add some entries
        self.cache.set("key1", "content1")
        self.cache.set("key2", "content2")
        
        # Create new cache instance with same directory
        new_cache = FileCache(
            cache_dir=self.temp_dir,
            max_size_mb=1,
            ttl_seconds=10
        )
        
        # Should detect existing entries
        stats = new_cache.get_stats()
        self.assertEqual(stats["file_count"], 2)
        
        # Should be able to retrieve existing entries
        self.assertEqual(new_cache.get("key1"), "content1")
        self.assertEqual(new_cache.get("key2"), "content2")
    
    def test_concurrent_access(self):
        """Test thread-safe concurrent access."""
        import threading
        import random
        
        results = []
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(10):
                    key = f"thread_{thread_id}_item_{i}"
                    content = f"Content from thread {thread_id}, item {i}"
                    
                    # Random operations
                    if random.random() < 0.7:
                        self.cache.set(key, content)
                    else:
                        self.cache.get(key)
                    
                    time.sleep(0.001)  # Small delay
                
                results.append(thread_id)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Should complete without errors
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 5)
        
        # Cache should be in consistent state
        stats = self.cache.get_stats()
        self.assertGreaterEqual(stats["file_count"], 0)
        self.assertLessEqual(stats["current_size_mb"], 1.0)


class TestFileCacheGlobalInstance(unittest.TestCase):
    """Test cases for global cache instance management."""
    
    def test_singleton_pattern(self):
        """Test that get_file_cache returns singleton instance."""
        cache1 = get_file_cache()
        cache2 = get_file_cache()
        
        self.assertIs(cache1, cache2)
    
    def test_clear_global_cache(self):
        """Test clearing global cache instance."""
        # Get instance
        cache = get_file_cache()
        cache.set("test_key", "test_content")
        
        # Clear global instance
        clear_file_cache()
        
        # New instance should be different
        new_cache = get_file_cache()
        self.assertIsNot(cache, new_cache)
        
        # Old data should not be accessible
        # (Note: files may still exist, but new instance has fresh state)
        stats = new_cache.get_stats()
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 0)
    
    @patch.dict(os.environ, {"ZEN_FILE_CACHE_SIZE": "50", "ZEN_CACHE_TTL": "1800"})
    def test_environment_configuration(self):
        """Test configuration from environment variables."""
        # Clear any existing instance
        clear_file_cache()
        
        # Get new instance with env config
        cache = get_file_cache()
        
        stats = cache.get_stats()
        self.assertEqual(stats["max_size_mb"], 50.0)
        self.assertEqual(cache.ttl, 1800)


if __name__ == "__main__":
    unittest.main()