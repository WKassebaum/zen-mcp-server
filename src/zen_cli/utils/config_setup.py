"""
Interactive configuration setup for Zen CLI

This module provides an interactive setup wizard for configuring the Zen CLI
environment, including storage backends, API keys, and cache settings.
"""

import os
import subprocess
import time
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
            'OPENROUTER_API_KEY',
            'XAI_API_KEY',
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
        click.echo("  file   - Local file storage (default)")
        click.echo("  redis  - Redis for distributed/team storage")
        click.echo("  memory - In-memory only (testing)")
        click.echo(f"\nCurrent: {current_storage}")
        
        storage_type = self._prompt_with_default(
            "Select storage type",
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
            
            # Check if Docker is available and offer to set up Redis
            if self._check_docker_available() and self._check_docker_compose_available():
                click.echo("\n🐳 Docker is available!")
                if click.confirm("Would you like to set up Redis using Docker?", default=True):
                    docker_config = self._setup_docker_redis()
                    if docker_config:
                        config.update(docker_config)
                        return config
                    else:
                        click.echo("\n📝 Falling back to manual Redis configuration...")
            
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
            current_password = self.current_config.get('REDIS_PASSWORD')
            if current_password:
                masked_password = self._mask_api_key(current_password)  # Reuse masking function
                click.echo(f"\nCurrent Redis password: {masked_password}")
                if click.confirm("Update Redis password?", default=False):
                    new_password = self._prompt_with_default(
                        "Redis password",
                        None,
                        password=True
                    )
                    if new_password:
                        config['REDIS_PASSWORD'] = new_password
            else:
                if click.confirm("Does your Redis require a password?", default=False):
                    config['REDIS_PASSWORD'] = self._prompt_with_default(
                        "Redis password",
                        None,
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
    
    def _mask_api_key(self, key: str) -> str:
        """Mask an API key showing first 6 and last 6 characters."""
        if not key:
            return ""
        if len(key) <= 14:
            # Key is too short to mask properly, just show partial
            return key[:3] + "..." + key[-3:] if len(key) > 6 else "***"
        return key[:6] + "..." + key[-6:]
    
    def _prompt_for_api_key(self, name: str, env_var: str, current_value: Optional[str]) -> Optional[str]:
        """Prompt for an API key with existing value handling."""
        if current_value:
            masked = self._mask_api_key(current_value)
            prompt = f"{name} API key [{masked}]"
            click.echo(f"Current: {masked}")
        else:
            masked = None
            prompt = f"{name} API key (not set)"
        
        # Prompt with password hiding
        value = click.prompt(
            prompt, 
            default='', 
            hide_input=True,
            show_default=False,
            type=str
        )
        
        # If empty and there's an existing value, keep it
        if not value and current_value:
            return None  # Don't update, keep existing
        elif value:
            return value  # Update with new value
        else:
            return None  # No existing value and no new value
    
    def setup_api_keys(self) -> Dict[str, str]:
        """Configure API keys."""
        click.echo("\n" + "="*60)
        click.echo("API KEY CONFIGURATION")
        click.echo("="*60)
        click.echo("\nPress Enter to keep existing values, or type new key.")
        click.echo("At least one API key is required for Zen CLI to function.")
        
        config = {}
        
        # API key configurations
        api_keys = [
            ('Gemini', 'GEMINI_API_KEY'),
            ('OpenAI', 'OPENAI_API_KEY'),
            ('OpenRouter', 'OPENROUTER_API_KEY'),
            ('X.AI (Grok)', 'XAI_API_KEY'),
        ]
        
        for name, env_var in api_keys:
            click.echo(f"\n{name}:")
            current_value = self.current_config.get(env_var)
            new_value = self._prompt_for_api_key(name, env_var, current_value)
            
            if new_value:  # Only add to config if there's a new value
                config[env_var] = new_value
        
        # Check if at least one API key is configured
        configured_keys = []
        for name, env_var in api_keys:
            if config.get(env_var) or self.current_config.get(env_var):
                configured_keys.append(name)
        
        if configured_keys:
            click.echo(f"\n✅ API keys configured for: {', '.join(configured_keys)}")
        else:
            click.echo("\n⚠️  Warning: No API keys configured. At least one is required.")
        
        return config
    
    def _check_docker_available(self) -> bool:
        """Check if Docker is installed and running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def _check_docker_compose_available(self) -> bool:
        """Check if Docker Compose is available."""
        try:
            # Try docker-compose first
            result = subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                return True
            
            # Try docker compose (v2 syntax)
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def _setup_docker_redis(self) -> Optional[Dict[str, str]]:
        """Set up Redis using Docker Compose."""
        # Try multiple locations for docker-compose.yaml
        search_paths = [
            # If running from development directory
            Path(__file__).parent.parent.parent.parent / "docker-compose.yaml",
            # Try common locations
            Path("/Users/wrk/WorkDev/MCP-Dev/zen-cli/docker-compose.yaml"),
            Path.home() / ".zen-cli" / "docker-compose.yaml",
            Path.cwd() / "docker-compose.yaml",
        ]
        
        docker_compose_file = None
        for path in search_paths:
            if path.exists():
                docker_compose_file = path
                break
        
        if not docker_compose_file:
            click.echo("⚠️  docker-compose.yaml not found. Searched locations:")
            for path in search_paths:
                click.echo(f"     - {path}")
            return None
        
        click.echo(f"\n📁 Found docker-compose.yaml at: {docker_compose_file}")
        
        # Ask for custom port if needed
        default_port = 6379
        custom_port = self._prompt_with_default(
            "Redis port",
            str(default_port),
            type_=int
        )
        
        # Create .env file for docker-compose if using custom port
        if custom_port != default_port:
            env_file = docker_compose_file.parent / ".env"
            with open(env_file, "w") as f:
                f.write(f"REDIS_PORT={custom_port}\n")
            click.echo(f"✅ Created .env file with REDIS_PORT={custom_port}")
        
        # Start Redis container
        click.echo("\n🚀 Starting Redis container...")
        try:
            # Determine which command to use
            compose_cmd = ["docker-compose"] if subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True
            ).returncode == 0 else ["docker", "compose"]
            
            # Run docker-compose up -d
            result = subprocess.run(
                compose_cmd + ["-f", str(docker_compose_file), "up", "-d"],
                capture_output=True,
                text=True,
                cwd=docker_compose_file.parent
            )
            
            if result.returncode != 0:
                click.echo(f"❌ Failed to start Redis container: {result.stderr}")
                return None
            
            click.echo("✅ Redis container started successfully!")
            
            # Wait for Redis to be ready
            click.echo("⏳ Waiting for Redis to be ready...")
            time.sleep(3)
            
            # Test connection
            config = {
                'REDIS_HOST': 'localhost',
                'REDIS_PORT': str(custom_port),
                'REDIS_DB': '0',
                'REDIS_KEY_PREFIX': 'zen:'
            }
            
            if self._test_redis_connection(config):
                click.echo("✅ Redis is ready and accepting connections!")
                return config
            else:
                click.echo("⚠️  Redis container started but connection test failed")
                click.echo("   You may need to wait a moment and try again")
                return config
                
        except Exception as e:
            click.echo(f"❌ Error starting Redis container: {e}")
            return None
    
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
                        display_value = self._mask_api_key(value)
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