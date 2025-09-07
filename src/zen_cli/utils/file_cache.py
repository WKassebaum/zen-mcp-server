"""
File-based cache with LRU eviction for API responses

This module provides a file-based cache with size-based LRU (Least Recently Used)
eviction policy. It's designed to cache API responses to disk with automatic
cleanup when the cache size exceeds the configured limit.

Key Features:
- File-based persistence in ~/.zen-cli/cache/
- LRU eviction when cache size exceeds limit
- Size-based limits (configurable in MB)
- Thread-safe operations with file locking
- TTL support for automatic expiration
- Atomic file operations to prevent corruption
- Cache statistics and monitoring
"""

import hashlib
import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FileCacheEntry:
    """Represents a cached file entry with metadata"""
    key: str
    file_path: str
    size_bytes: int
    created_at: float
    accessed_at: float
    expires_at: float
    access_count: int = 0
    metadata: Optional[Dict[str, Any]] = None


class FileCache:
    """
    File-based cache with LRU eviction policy.
    
    This cache stores API responses as files on disk with automatic eviction
    when the total cache size exceeds the configured limit. Files are evicted
    based on least recently used (LRU) policy.
    """
    
    def __init__(self, 
                 cache_dir: str = "~/.zen-cli/cache",
                 max_size_mb: int = 100,
                 ttl_seconds: int = 3600,
                 eviction_ratio: float = 0.2):
        """
        Initialize file cache with LRU eviction.
        
        Args:
            cache_dir: Directory to store cache files
            max_size_mb: Maximum cache size in megabytes
            ttl_seconds: Default time-to-live for cache entries
            eviction_ratio: Fraction of cache to evict when limit reached (0.2 = 20%)
        """
        self.cache_dir = Path(cache_dir).expanduser()
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.ttl = ttl_seconds
        self.eviction_ratio = eviction_ratio
        
        # Create cache directory structure
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = self.cache_dir / "data"
        self.meta_dir = self.cache_dir / "metadata"
        self.data_dir.mkdir(exist_ok=True)
        self.meta_dir.mkdir(exist_ok=True)
        
        # Thread safety
        self._lock = threading.Lock()
        self._file_locks = {}  # Per-file locks for finer granularity
        
        # Cache statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "current_size": 0,
            "file_count": 0
        }
        
        # Initialize cache state
        self._rebuild_cache_index()
        
        logger.info(
            f"FileCache initialized: dir={self.cache_dir}, "
            f"max_size={max_size_mb}MB, ttl={ttl_seconds}s"
        )
    
    def _rebuild_cache_index(self) -> None:
        """Rebuild cache index from existing files on startup."""
        with self._lock:
            total_size = 0
            file_count = 0
            
            # Clean up orphaned files and calculate current size
            for data_file in self.data_dir.glob("*.cache"):
                meta_file = self.meta_dir / f"{data_file.stem}.meta"
                
                if not meta_file.exists():
                    # Orphaned data file, remove it
                    logger.debug(f"Removing orphaned cache file: {data_file}")
                    data_file.unlink()
                    continue
                
                try:
                    # Load metadata to check expiration
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                    
                    # Check if expired
                    if time.time() >= meta.get("expires_at", 0):
                        logger.debug(f"Removing expired cache entry: {data_file.stem}")
                        data_file.unlink()
                        meta_file.unlink()
                        continue
                    
                    # Add to current size
                    total_size += data_file.stat().st_size
                    file_count += 1
                    
                except (json.JSONDecodeError, KeyError) as e:
                    # Corrupted metadata, remove both files
                    logger.debug(f"Removing corrupted cache entry: {data_file.stem}")
                    data_file.unlink()
                    meta_file.unlink()
            
            self.stats["current_size"] = total_size
            self.stats["file_count"] = file_count
            
            logger.info(
                f"Cache index rebuilt: {file_count} files, "
                f"{total_size / 1024 / 1024:.2f}MB"
            )
    
    def _generate_cache_key(self, content: str) -> str:
        """Generate a unique cache key using SHA-256 hash."""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_file_lock(self, key: str) -> threading.Lock:
        """Get or create a lock for a specific cache key."""
        if key not in self._file_locks:
            self._file_locks[key] = threading.Lock()
        return self._file_locks[key]
    
    def get(self, key: str) -> Optional[str]:
        """
        Retrieve cached content by key.
        
        Args:
            key: Cache key to retrieve
            
        Returns:
            Cached content string or None if not found/expired
        """
        file_lock = self._get_file_lock(key)
        
        with file_lock:
            data_file = self.data_dir / f"{key}.cache"
            meta_file = self.meta_dir / f"{key}.meta"
            
            if not data_file.exists() or not meta_file.exists():
                self.stats["misses"] += 1
                return None
            
            try:
                # Load metadata
                with open(meta_file, 'r') as f:
                    meta = json.load(f)
                
                # Check expiration
                if time.time() >= meta.get("expires_at", 0):
                    # Expired, remove files
                    self._remove_cache_entry(key)
                    self.stats["misses"] += 1
                    return None
                
                # Load data
                with open(data_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Update access time and count
                meta["accessed_at"] = time.time()
                meta["access_count"] = meta.get("access_count", 0) + 1
                
                # Save updated metadata
                with open(meta_file, 'w') as f:
                    json.dump(meta, f)
                
                self.stats["hits"] += 1
                logger.debug(f"Cache HIT: key={key[:8]}...")
                return content
                
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to read cache entry {key}: {e}")
                self._remove_cache_entry(key)
                self.stats["misses"] += 1
                return None
    
    def set(self, key: str, content: str, ttl: Optional[int] = None,
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store content in cache with optional TTL and metadata.
        
        Args:
            key: Cache key
            content: Content to cache
            ttl: Optional TTL override
            metadata: Optional metadata to store with entry
            
        Returns:
            True if successfully cached, False otherwise
        """
        file_lock = self._get_file_lock(key)
        
        with file_lock:
            data_file = self.data_dir / f"{key}.cache"
            meta_file = self.meta_dir / f"{key}.meta"
            
            # Calculate content size
            content_size = len(content.encode('utf-8'))
            
            # Check if we need to evict entries before adding new one
            with self._lock:
                if self.stats["current_size"] + content_size > self.max_size_bytes:
                    self._evict_lru_entries(content_size)
            
            try:
                # Write data file atomically
                temp_data = data_file.with_suffix('.tmp')
                with open(temp_data, 'w', encoding='utf-8') as f:
                    f.write(content)
                temp_data.replace(data_file)
                
                # Create metadata
                current_time = time.time()
                entry_meta = {
                    "key": key,
                    "file_path": str(data_file),
                    "size_bytes": content_size,
                    "created_at": current_time,
                    "accessed_at": current_time,
                    "expires_at": current_time + (ttl or self.ttl),
                    "access_count": 0,
                    "metadata": metadata
                }
                
                # Write metadata atomically
                temp_meta = meta_file.with_suffix('.tmp')
                with open(temp_meta, 'w') as f:
                    json.dump(entry_meta, f, indent=2)
                temp_meta.replace(meta_file)
                
                # Update statistics
                with self._lock:
                    self.stats["current_size"] += content_size
                    self.stats["file_count"] += 1
                
                logger.debug(
                    f"Cached: key={key[:8]}..., size={content_size/1024:.2f}KB, "
                    f"total_cache={self.stats['current_size']/1024/1024:.2f}MB"
                )
                return True
                
            except IOError as e:
                logger.error(f"Failed to cache entry {key}: {e}")
                # Clean up partial files
                for f in [data_file, meta_file, temp_data, temp_meta]:
                    try:
                        f.unlink()
                    except:
                        pass
                return False
    
    def _evict_lru_entries(self, required_space: int) -> None:
        """
        Evict least recently used entries to make space.
        
        Args:
            required_space: Bytes of space needed
        """
        # Get all cache entries with metadata
        entries = []
        for meta_file in self.meta_dir.glob("*.meta"):
            try:
                with open(meta_file, 'r') as f:
                    meta = json.load(f)
                entries.append(meta)
            except:
                # Skip corrupted entries
                continue
        
        # Sort by access time (oldest first)
        entries.sort(key=lambda x: x.get("accessed_at", 0))
        
        # Calculate how much space to free
        target_free = max(
            required_space,
            int(self.max_size_bytes * self.eviction_ratio)
        )
        
        freed_space = 0
        evicted_count = 0
        
        for entry in entries:
            if freed_space >= target_free:
                break
            
            key = entry.get("key")
            if key:
                size = entry.get("size_bytes", 0)
                if self._remove_cache_entry(key):
                    freed_space += size
                    evicted_count += 1
                    self.stats["evictions"] += 1
        
        logger.info(
            f"Evicted {evicted_count} entries, freed {freed_space/1024/1024:.2f}MB"
        )
    
    def _remove_cache_entry(self, key: str) -> bool:
        """
        Remove a cache entry (both data and metadata files).
        
        Args:
            key: Cache key to remove
            
        Returns:
            True if removed successfully
        """
        data_file = self.data_dir / f"{key}.cache"
        meta_file = self.meta_dir / f"{key}.meta"
        
        removed_size = 0
        
        try:
            if data_file.exists():
                removed_size = data_file.stat().st_size
                data_file.unlink()
            
            if meta_file.exists():
                meta_file.unlink()
            
            # Update statistics
            if removed_size > 0:
                self.stats["current_size"] -= removed_size
                self.stats["file_count"] -= 1
            
            return True
            
        except IOError as e:
            logger.error(f"Failed to remove cache entry {key}: {e}")
            return False
    
    def clear(self) -> int:
        """
        Clear all cache entries.
        
        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = 0
            
            # Remove all data files
            for data_file in self.data_dir.glob("*.cache"):
                try:
                    data_file.unlink()
                    count += 1
                except:
                    pass
            
            # Remove all metadata files
            for meta_file in self.meta_dir.glob("*.meta"):
                try:
                    meta_file.unlink()
                except:
                    pass
            
            # Reset statistics
            self.stats["current_size"] = 0
            self.stats["file_count"] = 0
            
            logger.info(f"Cleared {count} cache entries")
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total_requests = self.stats["hits"] + self.stats["misses"]
            hit_rate = (
                (self.stats["hits"] / total_requests * 100)
                if total_requests > 0 else 0
            )
            
            return {
                "hits": self.stats["hits"],
                "misses": self.stats["misses"],
                "evictions": self.stats["evictions"],
                "hit_rate_percent": round(hit_rate, 2),
                "current_size_mb": round(self.stats["current_size"] / 1024 / 1024, 2),
                "max_size_mb": self.max_size_bytes / 1024 / 1024,
                "file_count": self.stats["file_count"],
                "cache_dir": str(self.cache_dir)
            }
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.
        
        Returns:
            Number of expired entries removed
        """
        with self._lock:
            current_time = time.time()
            removed_count = 0
            
            for meta_file in self.meta_dir.glob("*.meta"):
                try:
                    with open(meta_file, 'r') as f:
                        meta = json.load(f)
                    
                    if current_time >= meta.get("expires_at", 0):
                        key = meta_file.stem
                        if self._remove_cache_entry(key):
                            removed_count += 1
                            
                except:
                    # Remove corrupted entries
                    key = meta_file.stem
                    self._remove_cache_entry(key)
                    removed_count += 1
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} expired cache entries")
            
            return removed_count


# Global cache instance
_file_cache_instance: Optional[FileCache] = None
_cache_lock = threading.Lock()


def get_file_cache(max_size_mb: Optional[int] = None,
                   ttl_seconds: Optional[int] = None) -> FileCache:
    """
    Get the global file cache instance.
    
    Args:
        max_size_mb: Optional max cache size override
        ttl_seconds: Optional TTL override
        
    Returns:
        Global FileCache instance
    """
    global _file_cache_instance
    
    if _file_cache_instance is None:
        with _cache_lock:
            if _file_cache_instance is None:
                # Use environment variables or defaults
                import os
                cache_size = max_size_mb or int(os.getenv("ZEN_FILE_CACHE_SIZE", "100"))
                cache_ttl = ttl_seconds or int(os.getenv("ZEN_CACHE_TTL", "3600"))
                
                _file_cache_instance = FileCache(
                    max_size_mb=cache_size,
                    ttl_seconds=cache_ttl
                )
    
    return _file_cache_instance


def clear_file_cache() -> None:
    """Clear the global file cache instance."""
    global _file_cache_instance
    if _file_cache_instance:
        _file_cache_instance.clear()
    _file_cache_instance = None
    logger.info("File cache instance cleared")