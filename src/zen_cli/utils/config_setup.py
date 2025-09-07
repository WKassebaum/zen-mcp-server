"""
Interactive configuration setup for Zen CLI

This module provides an interactive setup wizard for configuring the Zen CLI
environment, including storage backends, API keys, and cache settings.
"""

import os
from pathlib import Path
from typing import Dict, Optional, Any
import click
from dotenv import load_dotenv, set_key


class ConfigurationWizard:
    """Interactive configuration wizard for Zen CLI settings."""
    
    def __init__(self):
        self.config_dir = Path.home() / '.zen-cli'
        self.env_file = self.config_dir / '.env'
        self.current_config = {}
        
        # Load existing configuration
        if self.env_file.exists():
            load_dotenv(self.env_file)
            self.current_config = self._load_current_config()
    
    def _load_current_config(self) -> Dict[str, str]:
        """Load current configuration from environment."""
        config_keys = [
            'ZEN_STORAGE_TYPE',
            'REDIS_HOST',
            'REDIS_PORT',
            'REDIS_DB',
            'REDIS_PASSWORD',
            'REDIS_KEY_PREFIX',
            'ZEN_CACHE_TTL',
            'ZEN_FILE_CACHE_SIZE',
            'ZEN_CACHE_ENABLED',
            'GEMINI_API_KEY',
            'OPENAI_API_KEY',
        ]
        
        config = {}
        for key in config_keys:
            value = os.getenv(key)
            if value:
                config[key] = value
        return config
    
    def _prompt_with_default(self, prompt: str, default: Optional[str] = None, 
                           password: bool = False, type_=str) -> Any:
        """Prompt user with a default value."""
        if default:
            prompt_text = f"{prompt} [{default}]"
        else:
            prompt_text = prompt
            
        if password:
            value = click.prompt(prompt_text, hide_input=True, default=default or '', 
                               show_default=False, type=type_)
        else:
            value = click.prompt(prompt_text, default=default, type=type_)
        
        return value if value else default
    
    def setup_storage(self) -> Dict[str, str]:
        """Configure storage backend settings."""
        click.echo("\n" + "="*60)
        click.echo("STORAGE CONFIGURATION")
        click.echo("="*60)
        
        config = {}
        
        # Storage type selection
        current_storage = self.current_config.get('ZEN_STORAGE_TYPE', 'file')
        click.echo("\nStorage Backend Options:")
        click.echo("  1. file   - Local file storage (default)")
        click.echo("  2. redis  - Redis for distributed/team storage")
        click.echo("  3. memory - In-memory only (testing)")
        
        storage_type = self._prompt_with_default(
            "\nSelect storage type",
            current_storage
        ).lower()
        
        if storage_type not in ['file', 'redis', 'memory']:
            storage_type = 'file'
        
        config['ZEN_STORAGE_TYPE'] = storage_type
        
        # Redis configuration if selected
        if storage_type == 'redis':
            click.echo("\n" + "-"*40)
            click.echo("Redis Configuration")
            click.echo("-"*40)
            
            config['REDIS_HOST'] = self._prompt_with_default(
                "Redis host",
                self.current_config.get('REDIS_HOST', 'localhost')
            )
            
            config['REDIS_PORT'] = str(self._prompt_with_default(
                "Redis port",
                self.current_config.get('REDIS_PORT', '6379'),
                type_=int
            ))
            
            config['REDIS_DB'] = str(self._prompt_with_default(
                "Redis database number",
                self.current_config.get('REDIS_DB', '0'),
                type_=int
            ))
            
            # Password is optional
            if click.confirm("Does your Redis require a password?", default=False):
                config['REDIS_PASSWORD'] = self._prompt_with_default(
                    "Redis password",
                    self.current_config.get('REDIS_PASSWORD'),
                    password=True
                )
            
            config['REDIS_KEY_PREFIX'] = self._prompt_with_default(
                "Redis key prefix (for namespacing)",
                self.current_config.get('REDIS_KEY_PREFIX', 'zen:')
            )
            
            # Test Redis connection
            if click.confirm("\nTest Redis connection?", default=True):
                if self._test_redis_connection(config):
                    click.echo("✅ Redis connection successful!")
                else:
                    click.echo("⚠️  Could not connect to Redis. Settings saved anyway.")
                    click.echo("   Zen CLI will fall back to file storage if Redis is unavailable.")
        
        return config
    
    def setup_cache(self) -> Dict[str, str]:
        """Configure caching settings."""
        click.echo("\n" + "="*60)
        click.echo("CACHE CONFIGURATION")
        click.echo("="*60)
        
        config = {}
        
        # Cache enable/disable
        cache_enabled = self.current_config.get('ZEN_CACHE_ENABLED', 'true').lower() == 'true'
        config['ZEN_CACHE_ENABLED'] = 'true' if click.confirm(
            "\nEnable response caching?", 
            default=cache_enabled
        ) else 'false'
        
        if config['ZEN_CACHE_ENABLED'] == 'true':
            # Cache TTL
            current_ttl = int(self.current_config.get('ZEN_CACHE_TTL', '3600'))
            ttl_minutes = current_ttl // 60
            
            ttl_minutes = self._prompt_with_default(
                "Cache TTL in minutes",
                str(ttl_minutes),
                type_=int
            )
            config['ZEN_CACHE_TTL'] = str(ttl_minutes * 60)
            
            # File cache size
            current_size = int(self.current_config.get('ZEN_FILE_CACHE_SIZE', '100'))
            config['ZEN_FILE_CACHE_SIZE'] = str(self._prompt_with_default(
                "File cache size in MB",
                str(current_size),
                type_=int
            ))
        
        return config
    
    def setup_api_keys(self) -> Dict[str, str]:
        """Configure API keys."""
        click.echo("\n" + "="*60)
        click.echo("API KEY CONFIGURATION")
        click.echo("="*60)
        click.echo("\nNote: API keys are required for Zen CLI to function.")
        click.echo("Leave blank to keep existing values.")
        
        config = {}
        
        # Gemini API Key
        current_gemini = self.current_config.get('GEMINI_API_KEY')
        if current_gemini:
            masked_gemini = current_gemini[:10] + '...' + current_gemini[-4:]
            click.echo(f"\nCurrent Gemini API key: {masked_gemini}")
        
        if click.confirm("Update Gemini API key?", default=not bool(current_gemini)):
            config['GEMINI_API_KEY'] = self._prompt_with_default(
                "Gemini API key",
                None,
                password=True
            )
        
        # OpenAI API Key
        current_openai = self.current_config.get('OPENAI_API_KEY')
        if current_openai:
            masked_openai = current_openai[:10] + '...' + current_openai[-4:]
            click.echo(f"\nCurrent OpenAI API key: {masked_openai}")
        
        if click.confirm("Update OpenAI API key?", default=not bool(current_openai)):
            config['OPENAI_API_KEY'] = self._prompt_with_default(
                "OpenAI API key",
                None,
                password=True
            )
        
        return config
    
    def _test_redis_connection(self, config: Dict[str, str]) -> bool:
        """Test Redis connection with provided config."""
        try:
            import redis
            
            client = redis.Redis(
                host=config.get('REDIS_HOST', 'localhost'),
                port=int(config.get('REDIS_PORT', 6379)),
                db=int(config.get('REDIS_DB', 0)),
                password=config.get('REDIS_PASSWORD'),
                socket_timeout=2
            )
            client.ping()
            return True
        except ImportError:
            click.echo("ℹ️  Redis package not installed. Install with: pip install redis")
            return False
        except Exception as e:
            click.echo(f"Connection failed: {e}")
            return False
    
    def save_configuration(self, config: Dict[str, str]) -> None:
        """Save configuration to .env file."""
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Write each configuration value
        for key, value in config.items():
            if value is not None:  # Only write non-None values
                set_key(str(self.env_file), key, value)
        
        click.echo(f"\n✅ Configuration saved to {self.env_file}")
    
    def run_wizard(self, sections: Optional[list] = None) -> None:
        """Run the configuration wizard."""
        click.echo("\n" + "🧙"*30)
        click.echo("Welcome to the Zen CLI Configuration Wizard!")
        click.echo("🧙"*30)
        
        if self.env_file.exists():
            click.echo(f"\n📝 Existing configuration found at: {self.env_file}")
            click.echo("   Current values will be shown as defaults.")
        else:
            click.echo(f"\n📝 No configuration found. Creating new config at: {self.env_file}")
        
        all_config = {}
        
        # Determine which sections to configure
        if not sections:
            sections = ['storage', 'cache', 'api_keys']
        
        # Storage configuration
        if 'storage' in sections:
            if click.confirm("\nConfigure storage backend?", default=True):
                all_config.update(self.setup_storage())
        
        # Cache configuration
        if 'cache' in sections:
            if click.confirm("\nConfigure caching?", default=True):
                all_config.update(self.setup_cache())
        
        # API keys configuration
        if 'api_keys' in sections:
            if click.confirm("\nConfigure API keys?", default=True):
                all_config.update(self.setup_api_keys())
        
        # Save configuration
        if all_config:
            click.echo("\n" + "="*60)
            click.echo("CONFIGURATION SUMMARY")
            click.echo("="*60)
            
            for key, value in all_config.items():
                if 'PASSWORD' in key or 'API_KEY' in key:
                    if value:
                        display_value = value[:10] + '...' if len(value) > 10 else value
                    else:
                        display_value = '(unchanged)'
                else:
                    display_value = value
                click.echo(f"  {key}: {display_value}")
            
            if click.confirm("\nSave this configuration?", default=True):
                self.save_configuration(all_config)
                
                click.echo("\n" + "🎉"*20)
                click.echo("Configuration complete!")
                click.echo("\nTo use Redis storage, make sure Redis is running.")
                click.echo("Your settings will be loaded automatically when you run zen commands.")
                click.echo("🎉"*20)
        else:
            click.echo("\n👍 No changes made to configuration.")


def run_configuration_wizard(sections: Optional[list] = None):
    """Entry point for the configuration wizard."""
    wizard = ConfigurationWizard()
    wizard.run_wizard(sections)