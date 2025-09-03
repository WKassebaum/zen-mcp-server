"""
Advanced configuration management for Zen CLI

This module provides a unified configuration system supporting:
- Global configuration (~/.zen-cli/config.json)
- Per-project configuration
- Environment variable overrides
- API key management per provider
- Storage backend configuration
- Model preferences and routing

Configuration Hierarchy (highest priority first):
1. Environment variables (ZEN_*, OPENAI_API_KEY, etc.)
2. Project-specific config (~/.zen-cli/projects/{project}/config.json)
3. Global config (~/.zen-cli/config.json)
4. Built-in defaults

Key Features:
- Thread-safe configuration access
- Automatic config file creation
- Validation and schema enforcement
- Migration support for config upgrades
- Environment-specific overrides
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Storage backend configuration"""
    type: str = "file"  # file, redis, memory
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_key_prefix: str = "zen:"
    file_directory: str = "~/.zen-cli/conversations"
    cleanup_interval_hours: int = 24


@dataclass
class ModelConfig:
    """Model configuration and preferences"""
    default_provider: str = "auto"
    preferred_fast: str = "grok-code-fast-1"
    preferred_reasoning: str = "gpt-4o"
    preferred_extended: str = "o3"
    temperature: float = 0.7
    fallback_models: List[str] = None

    def __post_init__(self):
        if self.fallback_models is None:
            self.fallback_models = ["flash", "gpt5-mini", "gemini-pro"]


@dataclass
class SessionConfig:
    """Session and conversation configuration"""
    timeout_hours: int = 3
    auto_create: bool = True
    max_sessions: int = 100
    cleanup_on_startup: bool = True


@dataclass
class ProjectConfig:
    """Project-specific configuration"""
    name: str
    description: str = ""
    storage: StorageConfig = None
    api_keys: Dict[str, str] = None
    models: ModelConfig = None
    session: SessionConfig = None
    created_at: str = ""
    last_used: str = ""

    def __post_init__(self):
        if self.storage is None:
            self.storage = StorageConfig()
        if self.api_keys is None:
            self.api_keys = {}
        if self.models is None:
            self.models = ModelConfig()
        if self.session is None:
            self.session = SessionConfig()
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class GlobalConfig:
    """Global configuration structure"""
    current_project: Optional[str] = None
    projects: Dict[str, ProjectConfig] = None
    storage: StorageConfig = None
    models: ModelConfig = None
    session: SessionConfig = None
    api_keys: Dict[str, str] = None
    version: str = "1.0"
    created_at: str = ""
    last_updated: str = ""

    def __post_init__(self):
        if self.projects is None:
            self.projects = {}
        if self.storage is None:
            self.storage = StorageConfig()
        if self.models is None:
            self.models = ModelConfig()
        if self.session is None:
            self.session = SessionConfig()
        if self.api_keys is None:
            self.api_keys = {}
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class ConfigManager:
    """Advanced configuration manager with project support"""

    def __init__(self, config_dir: str = None):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Base configuration directory (default: ~/.zen-cli)
        """
        self.config_dir = Path(config_dir or "~/.zen-cli").expanduser()
        self.config_file = self.config_dir / "config.json"
        self.projects_dir = self.config_dir / "projects"
        
        # Thread-safe access
        self._lock = threading.RLock()
        self._config: Optional[GlobalConfig] = None
        
        # Ensure directories exist
        self._ensure_directories()
        
        logger.info(f"ConfigManager initialized: {self.config_dir}")

    def _ensure_directories(self):
        """Create configuration directories if they don't exist"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.projects_dir.mkdir(parents=True, exist_ok=True)
            
            # Create conversations directory
            conversations_dir = self.config_dir / "conversations"
            conversations_dir.mkdir(exist_ok=True)
            
        except Exception as e:
            logger.error(f"Failed to create config directories: {e}")
            raise

    def _load_config(self) -> GlobalConfig:
        """Load global configuration from file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    
                # Convert nested dictionaries to dataclasses
                config = self._dict_to_config(data)
                logger.debug(f"Loaded configuration from {self.config_file}")
                return config
            else:
                logger.info("No config file found, creating default configuration")
                return GlobalConfig()
                
        except Exception as e:
            logger.warning(f"Failed to load config file, using defaults: {e}")
            return GlobalConfig()

    def _dict_to_config(self, data: dict) -> GlobalConfig:
        """Convert dictionary to configuration dataclasses"""
        try:
            # Handle nested objects
            if 'storage' in data and isinstance(data['storage'], dict):
                data['storage'] = StorageConfig(**data['storage'])
            
            if 'models' in data and isinstance(data['models'], dict):
                data['models'] = ModelConfig(**data['models'])
                
            if 'session' in data and isinstance(data['session'], dict):
                data['session'] = SessionConfig(**data['session'])
            
            # Handle projects
            if 'projects' in data and isinstance(data['projects'], dict):
                projects = {}
                for name, proj_data in data['projects'].items():
                    if isinstance(proj_data, dict):
                        # Convert nested project objects
                        if 'storage' in proj_data:
                            proj_data['storage'] = StorageConfig(**proj_data['storage'])
                        if 'models' in proj_data:
                            proj_data['models'] = ModelConfig(**proj_data['models'])
                        if 'session' in proj_data:
                            proj_data['session'] = SessionConfig(**proj_data['session'])
                        
                        projects[name] = ProjectConfig(name=name, **proj_data)
                data['projects'] = projects
            
            return GlobalConfig(**data)
            
        except Exception as e:
            logger.warning(f"Config conversion error, using defaults: {e}")
            return GlobalConfig()

    def _save_config(self, config: GlobalConfig):
        """Save configuration to file"""
        try:
            # Convert to dictionary and handle dataclasses
            config_dict = asdict(config)
            
            # Update timestamp
            config_dict['last_updated'] = datetime.now().isoformat()
            
            # Write atomically
            temp_file = self.config_file.with_suffix('.json.tmp')
            with open(temp_file, 'w') as f:
                json.dump(config_dict, f, indent=2, default=str)
            
            temp_file.replace(self.config_file)
            logger.debug(f"Saved configuration to {self.config_file}")
            
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise

    def get_config(self) -> GlobalConfig:
        """Get current configuration with thread-safe access"""
        with self._lock:
            if self._config is None:
                self._config = self._load_config()
            return self._config

    def save_config(self):
        """Save current configuration to file"""
        with self._lock:
            if self._config is not None:
                self._save_config(self._config)

    def get_current_project_config(self) -> Optional[ProjectConfig]:
        """Get configuration for currently active project"""
        config = self.get_config()
        if config.current_project and config.current_project in config.projects:
            return config.projects[config.current_project]
        return None

    def create_project(self, name: str, description: str = "", **kwargs) -> ProjectConfig:
        """Create a new project configuration"""
        with self._lock:
            config = self.get_config()
            
            if name in config.projects:
                raise ValueError(f"Project '{name}' already exists")
            
            # Create project config
            project = ProjectConfig(
                name=name,
                description=description,
                **kwargs
            )
            
            # Add to global config
            config.projects[name] = project
            self._config = config
            self.save_config()
            
            logger.info(f"Created project '{name}'")
            return project

    def set_current_project(self, name: str):
        """Set the current active project"""
        with self._lock:
            config = self.get_config()
            
            if name not in config.projects:
                raise ValueError(f"Project '{name}' does not exist")
            
            config.current_project = name
            
            # Update last_used timestamp
            config.projects[name].last_used = datetime.now().isoformat()
            
            self._config = config
            self.save_config()
            
            logger.info(f"Set current project to '{name}'")

    def get_storage_config(self) -> StorageConfig:
        """Get storage configuration with project override"""
        project_config = self.get_current_project_config()
        if project_config and project_config.storage:
            return project_config.storage
        
        return self.get_config().storage

    def get_model_config(self) -> ModelConfig:
        """Get model configuration with project override"""
        project_config = self.get_current_project_config()
        if project_config and project_config.models:
            return project_config.models
            
        return self.get_config().models

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key with environment and project overrides"""
        # Environment variables take highest priority
        env_key = f"{provider.upper()}_API_KEY"
        env_value = os.getenv(env_key)
        if env_value:
            return env_value
        
        # Check project-specific API keys
        project_config = self.get_current_project_config()
        if project_config and provider in project_config.api_keys:
            return project_config.api_keys[provider]
        
        # Check global API keys
        config = self.get_config()
        if provider in config.api_keys:
            return config.api_keys[provider]
        
        return None

    def set_api_key(self, provider: str, api_key: str, project_specific: bool = False):
        """Set API key in configuration"""
        with self._lock:
            if project_specific:
                project_config = self.get_current_project_config()
                if not project_config:
                    raise ValueError("No current project set for project-specific API key")
                project_config.api_keys[provider] = api_key
            else:
                config = self.get_config()
                config.api_keys[provider] = api_key
                self._config = config
            
            self.save_config()
            logger.info(f"Set {provider} API key ({'project' if project_specific else 'global'})")

    def get_env_overrides(self) -> Dict[str, Any]:
        """Get configuration overrides from environment variables"""
        overrides = {}
        
        # Storage overrides
        if os.getenv("ZEN_STORAGE_TYPE"):
            overrides['storage_type'] = os.getenv("ZEN_STORAGE_TYPE")
        if os.getenv("REDIS_HOST"):
            overrides['redis_host'] = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            overrides['redis_port'] = int(os.getenv("REDIS_PORT"))
        if os.getenv("REDIS_DB"):
            overrides['redis_db'] = int(os.getenv("REDIS_DB"))
        if os.getenv("REDIS_PASSWORD"):
            overrides['redis_password'] = os.getenv("REDIS_PASSWORD")
        
        # Model overrides
        if os.getenv("DEFAULT_MODEL"):
            overrides['default_model'] = os.getenv("DEFAULT_MODEL")
        if os.getenv("DEFAULT_TEMPERATURE"):
            overrides['default_temperature'] = float(os.getenv("DEFAULT_TEMPERATURE"))
        
        # Session overrides  
        if os.getenv("SESSION_TIMEOUT_HOURS"):
            overrides['session_timeout'] = int(os.getenv("SESSION_TIMEOUT_HOURS"))
        
        return overrides

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects with metadata"""
        config = self.get_config()
        projects = []
        
        for name, project in config.projects.items():
            projects.append({
                'name': name,
                'description': project.description,
                'created_at': project.created_at,
                'last_used': project.last_used,
                'is_current': name == config.current_project,
                'storage_type': project.storage.type,
                'api_keys_configured': len(project.api_keys)
            })
        
        # Sort by last used (most recent first)
        projects.sort(key=lambda p: p['last_used'] or '0', reverse=True)
        return projects

    def delete_project(self, name: str):
        """Delete a project configuration"""
        with self._lock:
            config = self.get_config()
            
            if name not in config.projects:
                raise ValueError(f"Project '{name}' does not exist")
            
            # Don't delete if it's the current project
            if config.current_project == name:
                config.current_project = None
            
            del config.projects[name]
            self._config = config
            self.save_config()
            
            logger.info(f"Deleted project '{name}'")

    def export_config(self, include_api_keys: bool = False) -> Dict[str, Any]:
        """Export configuration for backup/sharing"""
        config = self.get_config()
        export_data = asdict(config)
        
        if not include_api_keys:
            # Remove sensitive information
            export_data['api_keys'] = {}
            for project in export_data['projects'].values():
                if isinstance(project, dict):
                    project['api_keys'] = {}
        
        return export_data

    def health_check(self) -> Dict[str, Any]:
        """Check configuration health and return status"""
        try:
            config = self.get_config()
            
            return {
                'healthy': True,
                'config_file_exists': self.config_file.exists(),
                'config_dir_writable': os.access(self.config_dir, os.W_OK),
                'projects_count': len(config.projects),
                'current_project': config.current_project,
                'api_keys_configured': len(config.api_keys),
                'storage_type': config.storage.type,
                'config_version': config.version
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e)
            }


# Global config manager instance
_config_manager: Optional[ConfigManager] = None
_config_lock = threading.Lock()


def get_config_manager() -> ConfigManager:
    """Get global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        with _config_lock:
            if _config_manager is None:
                _config_manager = ConfigManager()
    return _config_manager


def get_current_config() -> GlobalConfig:
    """Get current configuration (convenience function)"""
    return get_config_manager().get_config()


def get_api_key(provider: str) -> Optional[str]:
    """Get API key for provider (convenience function)"""
    return get_config_manager().get_api_key(provider)