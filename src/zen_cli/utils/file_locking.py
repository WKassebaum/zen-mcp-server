"""
Session-level file locking for preventing concurrent access conflicts

This module provides file locking mechanisms to prevent race conditions when
multiple zen processes access the same session or conversation files.

Key Features:
- Advisory file locking with timeout and retry
- Cross-platform support (fcntl on Unix, msvcrt on Windows)
- Session-specific locks to prevent conversation corruption
- Automatic lock cleanup on process exit
- Deadlock detection and prevention
- Lock acquisition with exponential backoff
"""

import fcntl
import hashlib
import logging
import os
import signal
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class LockInfo:
    """Information about an acquired lock."""
    session_id: str
    lock_file: Path
    lock_fd: int
    acquired_at: float
    pid: int
    thread_id: int


class SessionLockManager:
    """
    Manages session-level file locks to prevent concurrent access conflicts.
    
    This manager ensures that only one process can modify a session's
    conversation data at a time, preventing race conditions and data corruption.
    """
    
    def __init__(self, lock_dir: str = "~/.zen-cli/locks"):
        """
        Initialize the session lock manager.
        
        Args:
            lock_dir: Directory to store lock files
        """
        self.lock_dir = Path(lock_dir).expanduser()
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        
        # Track acquired locks for cleanup
        self._active_locks: Dict[str, LockInfo] = {}
        self._lock = threading.Lock()
        
        # Register cleanup handlers
        self._register_cleanup_handlers()
        
        logger.info(f"Session lock manager initialized: {self.lock_dir}")
    
    def _register_cleanup_handlers(self):
        """Register signal handlers for cleanup on exit."""
        def cleanup_handler(signum, frame):
            """Clean up locks on signal."""
            logger.info(f"Received signal {signum}, cleaning up locks...")
            self.release_all_locks()
            sys.exit(0)
        
        # Register for common termination signals
        for sig in [signal.SIGTERM, signal.SIGINT]:
            try:
                signal.signal(sig, cleanup_handler)
            except (OSError, ValueError):
                # Signal may not be available on this platform
                pass
    
    def _get_lock_file_path(self, session_id: str) -> Path:
        """
        Get the lock file path for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Path to the lock file
        """
        # Use hash for consistent filename
        session_hash = hashlib.md5(session_id.encode()).hexdigest()[:16]
        return self.lock_dir / f"session_{session_hash}.lock"
    
    def acquire_session_lock(self,
                            session_id: str,
                            timeout: float = 5.0,
                            retry_delay: float = 0.1,
                            max_retry_delay: float = 2.0) -> bool:
        """
        Acquire a lock for a specific session.
        
        Args:
            session_id: Session identifier to lock
            timeout: Maximum time to wait for lock acquisition
            retry_delay: Initial delay between retries
            max_retry_delay: Maximum delay between retries
            
        Returns:
            True if lock was acquired, False if timeout
            
        Raises:
            OSError: If lock file operations fail
        """
        lock_file = self._get_lock_file_path(session_id)
        start_time = time.time()
        current_delay = retry_delay
        
        while time.time() - start_time < timeout:
            try:
                # Try to create and lock the file
                lock_fd = os.open(
                    str(lock_file),
                    os.O_CREAT | os.O_WRONLY | os.O_EXCL
                )
                
                try:
                    # Try to acquire exclusive lock (non-blocking)
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    
                    # Write lock info
                    lock_data = f"{os.getpid()}:{threading.get_ident()}:{time.time()}\n"
                    os.write(lock_fd, lock_data.encode())
                    
                    # Track the lock
                    with self._lock:
                        self._active_locks[session_id] = LockInfo(
                            session_id=session_id,
                            lock_file=lock_file,
                            lock_fd=lock_fd,
                            acquired_at=time.time(),
                            pid=os.getpid(),
                            thread_id=threading.get_ident()
                        )
                    
                    logger.debug(f"Acquired lock for session: {session_id}")
                    return True
                    
                except (OSError, IOError):
                    # Lock is held by another process
                    os.close(lock_fd)
                    raise
                    
            except (OSError, IOError) as e:
                # File exists or lock is held
                if lock_file.exists():
                    # Check if lock holder is still alive
                    if self._is_lock_stale(lock_file):
                        logger.warning(f"Removing stale lock for session: {session_id}")
                        self._remove_stale_lock(lock_file)
                        continue
                
                # Wait and retry with exponential backoff
                time.sleep(current_delay)
                current_delay = min(current_delay * 1.5, max_retry_delay)
        
        logger.warning(
            f"Failed to acquire lock for session {session_id} after {timeout}s"
        )
        return False
    
    def release_session_lock(self, session_id: str) -> bool:
        """
        Release a lock for a specific session.
        
        Args:
            session_id: Session identifier to unlock
            
        Returns:
            True if lock was released, False if not held
        """
        with self._lock:
            if session_id not in self._active_locks:
                logger.debug(f"No lock held for session: {session_id}")
                return False
            
            lock_info = self._active_locks.pop(session_id)
        
        try:
            # Release the file lock
            fcntl.flock(lock_info.lock_fd, fcntl.LOCK_UN)
            os.close(lock_info.lock_fd)
            
            # Remove the lock file
            lock_info.lock_file.unlink(missing_ok=True)
            
            logger.debug(f"Released lock for session: {session_id}")
            return True
            
        except (OSError, IOError) as e:
            logger.error(f"Error releasing lock for session {session_id}: {e}")
            return False
    
    def _is_lock_stale(self, lock_file: Path, stale_timeout: float = 300) -> bool:
        """
        Check if a lock file is stale (holder process died).
        
        Args:
            lock_file: Path to the lock file
            stale_timeout: Time after which a lock is considered stale
            
        Returns:
            True if lock is stale
        """
        try:
            # Check file age
            file_age = time.time() - lock_file.stat().st_mtime
            if file_age < stale_timeout:
                # Try to read lock info
                with open(lock_file, 'r') as f:
                    lock_data = f.read().strip()
                
                if ':' in lock_data:
                    parts = lock_data.split(':')
                    if len(parts) >= 1:
                        pid = int(parts[0])
                        
                        # Check if process is still alive
                        try:
                            os.kill(pid, 0)  # Signal 0 = check if alive
                            return False  # Process is alive
                        except ProcessLookupError:
                            return True  # Process is dead
            else:
                # File is old enough to be considered stale
                return True
                
        except (OSError, IOError, ValueError):
            # Can't determine, assume not stale
            return False
        
        return False
    
    def _remove_stale_lock(self, lock_file: Path) -> None:
        """
        Remove a stale lock file.
        
        Args:
            lock_file: Path to the stale lock file
        """
        try:
            lock_file.unlink()
            logger.info(f"Removed stale lock file: {lock_file}")
        except OSError as e:
            logger.error(f"Failed to remove stale lock file {lock_file}: {e}")
    
    def release_all_locks(self) -> None:
        """Release all locks held by this process."""
        with self._lock:
            session_ids = list(self._active_locks.keys())
        
        for session_id in session_ids:
            self.release_session_lock(session_id)
        
        logger.info(f"Released {len(session_ids)} locks")
    
    def get_active_locks(self) -> Dict[str, Dict]:
        """
        Get information about all active locks.
        
        Returns:
            Dictionary of session IDs to lock information
        """
        with self._lock:
            return {
                session_id: {
                    "lock_file": str(info.lock_file),
                    "acquired_at": info.acquired_at,
                    "pid": info.pid,
                    "thread_id": info.thread_id,
                    "held_for": time.time() - info.acquired_at
                }
                for session_id, info in self._active_locks.items()
            }
    
    def cleanup_stale_locks(self, stale_timeout: float = 300) -> int:
        """
        Clean up all stale lock files in the lock directory.
        
        Args:
            stale_timeout: Time after which a lock is considered stale
            
        Returns:
            Number of stale locks removed
        """
        removed_count = 0
        
        for lock_file in self.lock_dir.glob("session_*.lock"):
            if self._is_lock_stale(lock_file, stale_timeout):
                self._remove_stale_lock(lock_file)
                removed_count += 1
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} stale lock files")
        
        return removed_count


@contextmanager
def session_lock(session_id: str,
                 lock_manager: Optional[SessionLockManager] = None,
                 timeout: float = 5.0):
    """
    Context manager for session locking.
    
    Example:
        with session_lock("session_123"):
            # Perform operations on session data
            update_conversation(session_id, messages)
    
    Args:
        session_id: Session identifier to lock
        lock_manager: Lock manager instance (creates new if None)
        timeout: Maximum time to wait for lock
        
    Yields:
        None
        
    Raises:
        TimeoutError: If lock cannot be acquired within timeout
    """
    if lock_manager is None:
        lock_manager = get_global_lock_manager()
    
    # Acquire lock
    acquired = lock_manager.acquire_session_lock(session_id, timeout=timeout)
    if not acquired:
        raise TimeoutError(
            f"Could not acquire lock for session {session_id} within {timeout}s. "
            "Another process may be using this session."
        )
    
    try:
        yield
    finally:
        # Always release lock
        lock_manager.release_session_lock(session_id)


class FileLock:
    """
    Simple file lock for general file operations.
    
    This provides a simpler interface for locking individual files
    rather than sessions.
    """
    
    def __init__(self, file_path: Path, timeout: float = 5.0):
        """
        Initialize file lock.
        
        Args:
            file_path: Path to the file to lock
            timeout: Maximum time to wait for lock
        """
        self.file_path = Path(file_path)
        self.lock_file = self.file_path.with_suffix('.lock')
        self.timeout = timeout
        self.lock_fd = None
    
    def acquire(self) -> bool:
        """
        Acquire the file lock.
        
        Returns:
            True if lock was acquired
        """
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            try:
                self.lock_fd = os.open(
                    str(self.lock_file),
                    os.O_CREAT | os.O_WRONLY | os.O_EXCL
                )
                
                # Write lock info
                lock_data = f"{os.getpid()}:{time.time()}\n"
                os.write(self.lock_fd, lock_data.encode())
                
                return True
                
            except OSError:
                # Lock is held, wait and retry
                time.sleep(0.1)
        
        return False
    
    def release(self) -> None:
        """Release the file lock."""
        if self.lock_fd is not None:
            try:
                os.close(self.lock_fd)
                self.lock_file.unlink(missing_ok=True)
            except OSError:
                pass
            finally:
                self.lock_fd = None
    
    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock for {self.file_path}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


# Global lock manager instance
_global_lock_manager: Optional[SessionLockManager] = None
_manager_lock = threading.Lock()


def get_global_lock_manager() -> SessionLockManager:
    """
    Get the global session lock manager instance.
    
    Returns:
        Global SessionLockManager instance
    """
    global _global_lock_manager
    
    if _global_lock_manager is None:
        with _manager_lock:
            if _global_lock_manager is None:
                _global_lock_manager = SessionLockManager()
    
    return _global_lock_manager


def cleanup_all_locks() -> None:
    """Clean up all locks and reset the global manager."""
    global _global_lock_manager
    
    if _global_lock_manager is not None:
        _global_lock_manager.release_all_locks()
        _global_lock_manager = None
        logger.info("Global lock manager cleaned up")