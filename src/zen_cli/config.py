"""
Configuration management for Zen CLI

Handles API keys, profiles, and settings stored in ~/.zen/config.yaml
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DEFAULT_CONFIG = {
    'active_profile': 'default',
    'api_endpoint': 'http://localhost:3001',
    'token_optimization': {
        'enabled': True,
        'mode': 'two_stage',
        'telemetry': True,
        'version': 'v5.12.0'
    },
    'profiles': {
        'default': {
            'api_keys': {
                'GEMINI_API_KEY': '',
                'OPENAI_API_KEY': '',
            },
            'model_preferences': {
                'default_model': 'auto',
                'temperature': 0.3,
                'thinking_mode': 'medium'
            }
        }
    }
}


def get_config_path() -> Path:
    """Get the configuration file path."""
    return Path.home() / '.zen' / 'config.yaml'


def load_config() -> Dict[str, Any]:
    """
    Load configuration from file or create default.
    
    Returns:
        Configuration dictionary
    """
    config_path = get_config_path()
    
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                # Merge with defaults for any missing keys
                return merge_configs(DEFAULT_CONFIG, config)
        except Exception as e:
            print(f"Warning: Error loading config: {e}")
            return DEFAULT_CONFIG.copy()
    else:
        # Create default config
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """
    Save configuration to file.
    
    Args:
        config: Configuration dictionary to save
    """
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def merge_configs(default: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge user config with defaults.
    
    Args:
        default: Default configuration
        user: User configuration
        
    Returns:
        Merged configuration
    """
    result = default.copy()
    
    for key, value in user.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


def get_api_key(key_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Get API key from environment or config.
    
    Args:
        key_name: Name of the API key
        config: Configuration dictionary (optional)
        
    Returns:
        API key value or None
    """
    # First check environment variables
    env_value = os.getenv(key_name)
    if env_value:
        return env_value
    
    # Then check config
    if config:
        profile = config.get('active_profile', 'default')
        profiles = config.get('profiles', {})
        profile_config = profiles.get(profile, {})
        api_keys = profile_config.get('api_keys', {})
        return api_keys.get(key_name)
    
    return None


def set_api_key(key_name: str, value: str, profile: Optional[str] = None) -> None:
    """
    Set API key in configuration.
    
    Args:
        key_name: Name of the API key
        value: API key value
        profile: Profile to set key in (uses active if None)
    """
    config = load_config()
    
    if profile is None:
        profile = config.get('active_profile', 'default')
    
    # Ensure profile exists
    if 'profiles' not in config:
        config['profiles'] = {}
    if profile not in config['profiles']:
        config['profiles'][profile] = {'api_keys': {}}
    if 'api_keys' not in config['profiles'][profile]:
        config['profiles'][profile]['api_keys'] = {}
    
    # Set the key
    config['profiles'][profile]['api_keys'][key_name] = value
    
    save_config(config)


def get_active_profile() -> str:
    """Get the active configuration profile."""
    config = load_config()
    return config.get('active_profile', 'default')


def set_active_profile(profile: str) -> None:
    """
    Set the active configuration profile.
    
    Args:
        profile: Profile name to activate
    """
    config = load_config()
    
    # Ensure profile exists
    if 'profiles' not in config:
        config['profiles'] = {}
    if profile not in config['profiles']:
        config['profiles'][profile] = {
            'api_keys': {},
            'model_preferences': DEFAULT_CONFIG['profiles']['default']['model_preferences'].copy()
        }
    
    config['active_profile'] = profile
    save_config(config)


def get_model_preferences(profile: Optional[str] = None) -> Dict[str, Any]:
    """
    Get model preferences for a profile.
    
    Args:
        profile: Profile name (uses active if None)
        
    Returns:
        Model preferences dictionary
    """
    config = load_config()
    
    if profile is None:
        profile = config.get('active_profile', 'default')
    
    profiles = config.get('profiles', {})
    profile_config = profiles.get(profile, {})
    
    return profile_config.get('model_preferences', 
                              DEFAULT_CONFIG['profiles']['default']['model_preferences'].copy())