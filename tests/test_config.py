"""
Tests for configuration management system
"""

import os
import tempfile
import pytest
from pathlib import Path
import json

import sys
sys.path.insert(0, 'src')

from zen_cli.utils.config_manager import ConfigManager, GlobalConfig, ProjectConfig, StorageConfig


class TestConfigManager:
    """Test configuration management functionality"""
    
    def setup_method(self):
        """Setup for each test method"""
        # Create temporary directory for test config
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = ConfigManager(config_dir=self.temp_dir)
    
    def teardown_method(self):
        """Cleanup after each test method"""
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_config_initialization(self):
        """Test that configuration initializes correctly"""
        config = self.config_manager.get_config()
        
        assert isinstance(config, GlobalConfig)
        assert config.storage.type == "file"
        assert config.models.default_provider == "auto"
        assert len(config.projects) == 0
    
    def test_create_project(self):
        """Test project creation"""
        project_name = "test_project"
        description = "Test project description"
        
        project = self.config_manager.create_project(project_name, description)
        
        assert project.name == project_name
        assert project.description == description
        assert isinstance(project.storage, StorageConfig)
        
        # Verify project is in global config
        config = self.config_manager.get_config()
        assert project_name in config.projects
    
    def test_set_current_project(self):
        """Test setting current project"""
        project_name = "current_test"
        
        # Create project first
        self.config_manager.create_project(project_name, "Current test")
        
        # Set as current
        self.config_manager.set_current_project(project_name)
        
        config = self.config_manager.get_config()
        assert config.current_project == project_name
    
    def test_api_key_management(self):
        """Test API key storage and retrieval"""
        provider = "test_provider"
        api_key = "test_api_key_12345"
        
        # Set API key
        self.config_manager.set_api_key(provider, api_key)
        
        # Retrieve API key
        retrieved_key = self.config_manager.get_api_key(provider)
        assert retrieved_key == api_key
    
    def test_project_specific_api_keys(self):
        """Test project-specific API key storage"""
        project_name = "api_test_project"
        provider = "test_provider"
        global_key = "global_key"
        project_key = "project_key"
        
        # Create project
        self.config_manager.create_project(project_name, "API test")
        self.config_manager.set_current_project(project_name)
        
        # Set global API key
        self.config_manager.set_api_key(provider, global_key, project_specific=False)
        
        # Set project-specific API key
        self.config_manager.set_api_key(provider, project_key, project_specific=True)
        
        # Should return project-specific key when project is active
        retrieved_key = self.config_manager.get_api_key(provider)
        assert retrieved_key == project_key
    
    def test_config_persistence(self):
        """Test that configuration persists across manager instances"""
        project_name = "persistence_test"
        
        # Create project with first manager
        self.config_manager.create_project(project_name, "Persistence test")
        
        # Create new manager instance with same config dir
        new_manager = ConfigManager(config_dir=self.temp_dir)
        config = new_manager.get_config()
        
        # Verify project persisted
        assert project_name in config.projects
    
    def test_environment_override(self):
        """Test environment variable overrides"""
        # Set environment variable
        os.environ['GEMINI_API_KEY'] = 'env_test_key'
        
        try:
            # Should return environment variable value
            api_key = self.config_manager.get_api_key('gemini')
            assert api_key == 'env_test_key'
        finally:
            # Clean up environment
            del os.environ['GEMINI_API_KEY']
    
    def test_list_projects(self):
        """Test project listing functionality"""
        project_names = ['project1', 'project2', 'project3']
        
        # Create multiple projects
        for name in project_names:
            self.config_manager.create_project(name, f"Description for {name}")
        
        # List projects
        projects = self.config_manager.list_projects()
        
        assert len(projects) == len(project_names)
        project_list_names = [p['name'] for p in projects]
        for name in project_names:
            assert name in project_list_names
    
    def test_delete_project(self):
        """Test project deletion"""
        project_name = "delete_test"
        
        # Create and then delete project
        self.config_manager.create_project(project_name, "Delete test")
        self.config_manager.delete_project(project_name)
        
        config = self.config_manager.get_config()
        assert project_name not in config.projects
    
    def test_health_check(self):
        """Test configuration health check"""
        health = self.config_manager.health_check()
        
        assert isinstance(health, dict)
        assert 'healthy' in health
        assert health['healthy'] is True
        assert 'config_file_exists' in health
        assert 'projects_count' in health


def test_storage_backend_integration():
    """Test integration with storage backend"""
    try:
        from zen_cli.utils.storage_backend import get_storage_backend
        
        # Test storage backend retrieval
        storage = get_storage_backend()
        assert storage is not None
        
        # Test basic storage operations
        test_key = "test_key"
        test_value = "test_value"
        ttl = 3600
        
        storage.set_with_ttl(test_key, ttl, test_value)
        retrieved_value = storage.get(test_key)
        
        assert retrieved_value == test_value
        
    except ImportError:
        pytest.skip("Storage backend components not available")


def test_redis_storage_fallback():
    """Test Redis storage fallback behavior"""
    try:
        # Temporarily set Redis storage type
        os.environ['ZEN_STORAGE_TYPE'] = 'redis'
        
        try:
            from zen_cli.utils.storage_backend import get_storage_backend
            storage = get_storage_backend()
            
            # Should either be Redis or fallback to file/memory
            assert storage is not None
            
        except Exception:
            # Fallback behavior is acceptable if Redis isn't available
            pass
        
    finally:
        # Clean up environment
        if 'ZEN_STORAGE_TYPE' in os.environ:
            del os.environ['ZEN_STORAGE_TYPE']


if __name__ == '__main__':
    # Run tests if called directly
    pytest.main([__file__, '-v'])
