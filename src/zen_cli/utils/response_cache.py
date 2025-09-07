"""
Response caching for AI model API calls

This module provides caching functionality for AI model responses to reduce
redundant API calls and improve performance. It uses the existing storage
backend system for persistence across sessions.

Key Features:
- Content-based cache keys using SHA-256 hashing
- TTL support for automatic cache expiration
- Model-specific caching to avoid cross-model pollution
- Token count tracking for usage optimization
- Cache hit/miss metrics for monitoring
"""

import hashlib
import json
import logging
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict

from .storage_backend import get_storage_backend

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Represents a cached response entry"""
    response: str
    model: str
    timestamp: float
    prompt_hash: str
    prompt_preview: str  # First 100 chars for debugging
    token_count: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class ResponseCache:
    """
    Cache for AI model responses with TTL and storage backend integration.
    
    This cache reduces API calls by storing responses keyed by prompt content.
    It integrates with the multi-backend storage system (Redis/File/Memory).
    """
    
    def __init__(self, ttl_seconds: int = 3600, prefix: str = "response_cache"):
        """
        Initialize response cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries (default: 1 hour)
            prefix: Key prefix for namespacing cache entries
        """
        self.storage = get_storage_backend()
        self.ttl = ttl_seconds
        self.prefix = prefix
        
        # Metrics tracking
        self.hits = 0
        self.misses = 0
        self.total_saved_tokens = 0
        
        logger.info(f"Response cache initialized with TTL={ttl_seconds}s, prefix='{prefix}'")
    
    def _generate_cache_key(self, prompt: str, model: str, **kwargs) -> str:
        """
        Generate a unique cache key based on prompt and parameters.
        
        Args:
            prompt: The prompt text
            model: Model name
            **kwargs: Additional parameters that affect the response
            
        Returns:
            Cache key string
        """
        # Create a deterministic string from all inputs
        cache_components = {
            "prompt": prompt,
            "model": model,
            **kwargs
        }
        
        # Sort keys for consistent ordering
        cache_string = json.dumps(cache_components, sort_keys=True)
        
        # Generate SHA-256 hash
        prompt_hash = hashlib.sha256(cache_string.encode()).hexdigest()
        
        # Return namespaced key
        return f"{self.prefix}:{model}:{prompt_hash}"
    
    def get(self, prompt: str, model: str, **kwargs) -> Optional[str]:
        """
        Retrieve cached response if available.
        
        Args:
            prompt: The prompt to look up
            model: Model name
            **kwargs: Additional parameters used in key generation
            
        Returns:
            Cached response string or None if not found/expired
        """
        cache_key = self._generate_cache_key(prompt, model, **kwargs)
        
        try:
            cached_data = self.storage.get(cache_key)
            
            if cached_data:
                # Parse the cached entry
                entry_dict = json.loads(cached_data)
                entry = CacheEntry(**entry_dict)
                
                # Check if the entry is still valid
                age = time.time() - entry.timestamp
                if age <= self.ttl:
                    self.hits += 1
                    if entry.token_count:
                        self.total_saved_tokens += entry.token_count
                    
                    logger.debug(
                        f"Cache HIT for model={model}, age={age:.1f}s, "
                        f"saved_tokens={entry.token_count or 'unknown'}"
                    )
                    return entry.response
                else:
                    logger.debug(f"Cache EXPIRED for model={model}, age={age:.1f}s > TTL={self.ttl}s")
            
            self.misses += 1
            logger.debug(f"Cache MISS for model={model}")
            return None
            
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid cache entry for key {cache_key}: {e}")
            self.misses += 1
            return None
        except Exception as e:
            logger.error(f"Error retrieving cache for key {cache_key}: {e}")
            self.misses += 1
            return None
    
    def set(self, prompt: str, model: str, response: str, 
            token_count: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None,
            **kwargs) -> bool:
        """
        Cache a model response.
        
        Args:
            prompt: The prompt that generated this response
            model: Model name
            response: The response to cache
            token_count: Optional token count for metrics
            metadata: Optional metadata to store with the response
            **kwargs: Additional parameters used in key generation
            
        Returns:
            True if successfully cached, False otherwise
        """
        cache_key = self._generate_cache_key(prompt, model, **kwargs)
        prompt_hash = cache_key.split(":")[-1]  # Extract hash from key
        
        # Create cache entry
        entry = CacheEntry(
            response=response,
            model=model,
            timestamp=time.time(),
            prompt_hash=prompt_hash,
            prompt_preview=prompt[:100] if len(prompt) > 100 else prompt,
            token_count=token_count,
            metadata=metadata
        )
        
        try:
            # Serialize and store with TTL
            entry_json = json.dumps(asdict(entry))
            self.storage.set_with_ttl(cache_key, self.ttl, entry_json)
            
            logger.debug(
                f"Cached response for model={model}, "
                f"response_size={len(response)}, tokens={token_count or 'unknown'}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache response: {e}")
            return False
    
    def invalidate(self, prompt: str, model: str, **kwargs) -> bool:
        """
        Invalidate a specific cache entry.
        
        Args:
            prompt: The prompt to invalidate
            model: Model name
            **kwargs: Additional parameters used in key generation
            
        Returns:
            True if entry was deleted, False if not found
        """
        cache_key = self._generate_cache_key(prompt, model, **kwargs)
        
        try:
            if hasattr(self.storage, 'delete'):
                return self.storage.delete(cache_key)
            else:
                # Fallback for storage backends without delete
                logger.warning("Storage backend does not support deletion")
                return False
                
        except Exception as e:
            logger.error(f"Failed to invalidate cache entry: {e}")
            return False
    
    def clear_model_cache(self, model: str) -> int:
        """
        Clear all cache entries for a specific model.
        
        Args:
            model: Model name to clear cache for
            
        Returns:
            Number of entries cleared
        """
        pattern = f"{self.prefix}:{model}:*"
        cleared = 0
        
        try:
            # This requires backend support for pattern matching
            if hasattr(self.storage, 'delete_pattern'):
                cleared = self.storage.delete_pattern(pattern)
            else:
                logger.warning("Storage backend does not support pattern deletion")
                
        except Exception as e:
            logger.error(f"Failed to clear model cache: {e}")
            
        logger.info(f"Cleared {cleared} cache entries for model={model}")
        return cleared
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get cache performance metrics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": total_requests,
            "hit_rate_percent": round(hit_rate, 2),
            "total_saved_tokens": self.total_saved_tokens,
            "ttl_seconds": self.ttl,
            "storage_backend": self.storage.__class__.__name__
        }
    
    def reset_metrics(self) -> None:
        """Reset cache metrics to zero."""
        self.hits = 0
        self.misses = 0
        self.total_saved_tokens = 0
        logger.info("Cache metrics reset")


# Global cache instance (singleton)
_response_cache_instance: Optional[ResponseCache] = None


def get_response_cache(ttl_seconds: Optional[int] = None) -> ResponseCache:
    """
    Get the global response cache instance.
    
    Args:
        ttl_seconds: Optional TTL override for the cache
        
    Returns:
        Global ResponseCache instance
    """
    global _response_cache_instance
    
    if _response_cache_instance is None:
        # Use environment variable or default TTL
        import os
        default_ttl = int(os.getenv("ZEN_CACHE_TTL", "3600"))
        ttl = ttl_seconds or default_ttl
        
        _response_cache_instance = ResponseCache(ttl_seconds=ttl)
    
    return _response_cache_instance


def clear_response_cache() -> None:
    """Clear the global response cache instance."""
    global _response_cache_instance
    _response_cache_instance = None
    logger.info("Response cache instance cleared")