"""
File-based storage backend for conversation threads

This module provides a file-based persistent storage alternative to in-memory storage
for conversation contexts. It stores conversations in ~/.zen/ for persistence
across CLI invocations.

Key Features:
- File-based persistence in ~/.zen/conversations/
- TTL support with expiration metadata in files
- Thread-safe file operations with locks
- Automatic directory creation
- Background cleanup of expired conversations
- Drop-in replacement for InMemoryStorage
- Auto-session management with idempotent identity
"""

import hashlib
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .storage_base import StorageBackend

logger = logging.getLogger(__name__)


class FileBasedStorage(StorageBackend):
    """File-based storage for conversation threads with persistence"""

    def __init__(self, storage_dir: str = "~/.zen"):
        self.storage_dir = Path(storage_dir).expanduser()
        self.conversations_dir = self.storage_dir / "conversations"
        self._lock = threading.Lock()

        # Create directories if they don't exist
        self.storage_dir.mkdir(exist_ok=True)
        self.conversations_dir.mkdir(exist_ok=True)

        # Cleanup settings
        timeout_hours = int(os.getenv("CONVERSATION_TIMEOUT_HOURS", "3"))
        self._cleanup_interval = (timeout_hours * 3600) // 10
        self._cleanup_interval = max(300, self._cleanup_interval)  # Minimum 5 minutes
        self._shutdown = False

        # Start background cleanup thread (disabled in CLI mode to prevent hanging)
        # TODO: Fix thread interaction with CLI frameworks
        if os.getenv("ZEN_CLI_MODE") != "1":
            self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
            self._cleanup_thread.start()
        else:
            self._cleanup_thread = None

        logger.info(
            f"File-based storage initialized in {self.conversations_dir} with {timeout_hours}h timeout, cleanup every {self._cleanup_interval//60}m"
        )

    def _get_file_path(self, key: str) -> Path:
        """Get file path for a conversation key"""
        # Sanitize key for filename
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.conversations_dir / f"{safe_key}.json"

    def set(self, key: str, value: dict[str, Any], ttl: Optional[int] = None) -> None:
        """Store value with optional TTL (implements StorageBackend interface)"""
        ttl_seconds = ttl or 10800  # Default 3 hours
        with self._lock:
            expires_at = time.time() + ttl_seconds
            data = {"value": value, "expires_at": expires_at, "created_at": time.time()}  # Store dict directly

            file_path = self._get_file_path(key)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.debug(f"Stored key {key} with TTL {ttl_seconds}s in {file_path}")
            except Exception as e:
                logger.error(f"Failed to store key {key}: {e}")

    def get(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve value from file if not expired (implements StorageBackend interface)"""
        with self._lock:
            file_path = self._get_file_path(key)

            if not file_path.exists():
                return None

            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)

                expires_at = data.get("expires_at", 0)
                if time.time() < expires_at:
                    logger.debug(f"Retrieved key {key}")
                    return data["value"]  # Return dict
                else:
                    # Clean up expired entry
                    file_path.unlink()
                    logger.debug(f"Key {key} expired and removed")

            except Exception as e:
                logger.error(f"Failed to read key {key}: {e}")
                # Remove corrupted file
                try:
                    file_path.unlink()
                except Exception:
                    pass

        return None

    def delete(self, key: str) -> None:
        """Delete a value from storage"""
        with self._lock:
            file_path = self._get_file_path(key)
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.debug(f"Deleted key {key}")
                except Exception as e:
                    logger.error(f"Failed to delete key {key}: {e}")

    def exists(self, key: str) -> bool:
        """Check if a key exists and is not expired"""
        file_path = self._get_file_path(key)
        if not file_path.exists():
            return False

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            expires_at = data.get("expires_at", 0)
            return time.time() < expires_at
        except Exception:
            return False

    def list_keys(self, pattern: str = "*") -> list[str]:
        """List all keys matching pattern"""
        with self._lock:
            keys = []
            current_time = time.time()
            for file_path in self.conversations_dir.glob("*.json"):
                try:
                    with open(file_path, encoding="utf-8") as f:
                        data = json.load(f)
                    expires_at = data.get("expires_at", 0)
                    if current_time < expires_at:
                        key = file_path.stem
                        if pattern == "*" or key.startswith(pattern.rstrip("*")):
                            keys.append(key)
                except Exception:
                    pass  # Skip corrupted files
            return keys

    def list_active_conversations(self) -> list[tuple[str, dict]]:
        """List all active (non-expired) conversation keys with metadata"""
        active_conversations = []
        current_time = time.time()

        with self._lock:
            for file_path in self.conversations_dir.glob("*.json"):
                try:
                    with open(file_path, encoding="utf-8") as f:
                        data = json.load(f)

                    expires_at = data.get("expires_at", 0)
                    if current_time < expires_at:
                        key = file_path.stem
                        metadata = {
                            "created_at": data.get("created_at", 0),
                            "expires_at": expires_at,
                            "file_path": str(file_path),
                        }
                        active_conversations.append((key, metadata))

                except Exception as e:
                    logger.debug(f"Skipping corrupted conversation file {file_path}: {e}")

        return sorted(active_conversations, key=lambda x: x[1]["created_at"], reverse=True)

    def _cleanup_worker(self):
        """Background thread that periodically cleans up expired entries"""
        while not self._shutdown:
            time.sleep(self._cleanup_interval)
            self._cleanup_expired()

    def _cleanup_expired(self):
        """Remove all expired conversation files"""
        with self._lock:
            current_time = time.time()
            expired_count = 0

            for file_path in self.conversations_dir.glob("*.json"):
                try:
                    with open(file_path, encoding="utf-8") as f:
                        data = json.load(f)

                    expires_at = data.get("expires_at", 0)
                    if current_time >= expires_at:
                        file_path.unlink()
                        expired_count += 1

                except Exception as e:
                    # Remove corrupted files
                    logger.debug(f"Removing corrupted conversation file {file_path}: {e}")
                    try:
                        file_path.unlink()
                        expired_count += 1
                    except Exception:
                        pass

            if expired_count > 0:
                logger.debug(f"Cleaned up {expired_count} expired conversation files")

    def shutdown(self):
        """Graceful shutdown of background thread"""
        self._shutdown = True
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1)


class SessionManager:
    """Manages auto-session creation with idempotent identity"""

    def __init__(self, storage: FileBasedStorage):
        self.storage = storage
        self._session_cache = {}

    def get_session_identity(self) -> str:
        """Generate idempotent session identity based on context"""
        # Base identity on current working directory
        cwd = os.getcwd()

        # Try to get git commit hash for more specific identity
        git_hash = self._get_git_hash()

        # Create identity components
        identity_parts = [cwd]
        if git_hash:
            identity_parts.append(git_hash[:8])  # Short git hash

        # Add timestamp rounded to hour for session grouping
        hour_timestamp = int(time.time() // 3600) * 3600
        identity_parts.append(str(hour_timestamp))

        # Create hash of identity components
        identity_string = "|".join(identity_parts)
        session_hash = hashlib.md5(identity_string.encode()).hexdigest()[:16]

        return f"auto_{session_hash}"

    def _get_git_hash(self) -> Optional[str]:
        """Get current git commit hash if in a git repository"""
        try:
            result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_or_create_auto_session(self) -> str:
        """Get or create an auto-session based on current context"""
        session_id = self.get_session_identity()

        # Check if session already exists
        existing_thread = self.storage.get(f"thread:{session_id}")
        if existing_thread:
            logger.debug(f"Resuming auto-session: {session_id}")
            return session_id

        # Session doesn't exist, will be created when first conversation is started
        logger.debug(f"Auto-session identity: {session_id}")
        return session_id


# Global singleton instances
_storage_instance = None
_session_manager = None
_storage_lock = threading.Lock()


def get_storage_backend() -> FileBasedStorage:
    """Get the global file-based storage instance (singleton pattern)"""
    global _storage_instance
    if _storage_instance is None:
        with _storage_lock:
            if _storage_instance is None:
                # Check if user wants file-based storage (default for CLI)
                storage_type = os.getenv("ZEN_STORAGE_TYPE", "file").lower()
                if storage_type == "file":
                    _storage_instance = FileBasedStorage()
                    logger.info("Initialized file-based conversation storage")
                else:
                    # Fall back to in-memory storage
                    from .storage_base import InMemoryStorage

                    _storage_instance = InMemoryStorage()
                    logger.info("Initialized in-memory conversation storage")
    return _storage_instance


def get_session_manager() -> SessionManager:
    """Get the global session manager instance"""
    global _session_manager
    if _session_manager is None:
        with _storage_lock:
            if _session_manager is None:
                storage = get_storage_backend()
                _session_manager = SessionManager(storage)
                logger.info("Initialized session manager")
    return _session_manager
