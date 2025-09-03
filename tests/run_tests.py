#!/usr/bin/env python3
"""
Test runner for zen-cli test suite
"""

import sys
import os
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def run_tests():
    """Run all tests and report results"""
    test_dir = Path(__file__).parent
    
    print("🧪 Running Zen CLI Test Suite")
    print("=" * 50)
    
    # Find all test files
    test_files = list(test_dir.glob("test_*.py"))
    
    if not test_files:
        print("❌ No test files found!")
        return False
    
    print(f"📁 Found {len(test_files)} test files:")
    for test_file in test_files:
        print(f"  - {test_file.name}")
    print()
    
    # Run tests with pytest if available
    try:
        import pytest
        
        print("🚀 Running tests with pytest...")
        result = pytest.main([
            str(test_dir),
            '-v',
            '--tb=short',
            '--color=yes'
        ])
        
        if result == 0:
            print("\n✅ All tests passed!")
            return True
        else:
            print(f"\n❌ Some tests failed (exit code: {result})")
            return False
            
    except ImportError:
        print("⚠️ pytest not available, running tests individually...")
        
        # Run each test file individually
        passed = 0
        failed = 0
        
        for test_file in test_files:
            print(f"\n🔍 Running {test_file.name}...")
            try:
                # Import and run the test module
                spec = importlib.util.spec_from_file_location("test_module", test_file)
                test_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(test_module)
                
                # Look for test functions and classes
                test_count = 0
                for name in dir(test_module):
                    if name.startswith('test_') or (name.startswith('Test') and name != 'Test'):
                        test_count += 1
                
                print(f"  ✅ {test_file.name} completed ({test_count} tests)")
                passed += 1
                
            except Exception as e:
                print(f"  ❌ {test_file.name} failed: {e}")
                failed += 1
        
        print(f"\n📊 Test Summary: {passed} passed, {failed} failed")
        return failed == 0


def check_dependencies():
    """Check if test dependencies are available"""
    print("🔍 Checking test dependencies...")
    
    missing_deps = []
    
    # Check pytest
    try:
        import pytest
        print("  ✅ pytest available")
    except ImportError:
        print("  ⚠️ pytest not available (will use basic runner)")
    
    # Check core dependencies
    deps_to_check = [
        'asyncio',
        'pathlib', 
        'tempfile',
        'unittest.mock'
    ]
    
    for dep in deps_to_check:
        try:
            __import__(dep)
            print(f"  ✅ {dep} available")
        except ImportError:
            print(f"  ❌ {dep} missing")
            missing_deps.append(dep)
    
    if missing_deps:
        print(f"\n❌ Missing dependencies: {', '.join(missing_deps)}")
        return False
    
    print("✅ All dependencies available")
    return True


if __name__ == '__main__':
    print("Zen CLI Test Runner")
    print("==================\n")
    
    # Check dependencies first
    if not check_dependencies():
        sys.exit(1)
    
    print()
    
    # Run tests
    if run_tests():
        sys.exit(0)
    else:
        sys.exit(1)