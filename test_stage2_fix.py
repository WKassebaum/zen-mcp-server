#!/usr/bin/env python3
"""Test script to verify Stage 2 serialization fix"""

import json
import asyncio
from tools.mode_executor import ModeExecutor, DebugWorkflowRequest

async def test_schema_generation():
    """Test that schema generation doesn't fail with PydanticUndefinedType"""
    print("Testing Stage 2 schema generation fix...")
    
    # Create a mode executor for debug workflow
    executor = ModeExecutor("debug", "workflow")
    
    try:
        # Get the input schema (this is where the error was occurring)
        schema = executor.get_input_schema()
        
        # Try to serialize it to JSON (this would fail before the fix)
        json_schema = json.dumps(schema, indent=2)
        
        print("✅ Schema generation successful!")
        print(f"Schema size: {len(json_schema)} bytes")
        print("\nGenerated schema:")
        print(json_schema[:500] + "..." if len(json_schema) > 500 else json_schema)
        
        # Test with actual request model
        request_model = executor._get_request_model()
        if request_model:
            print(f"\n✅ Request model: {request_model.__name__}")
            
            # Test creating an instance
            test_request = {
                "step": "Test step",
                "step_number": 1,
                "findings": "Test findings",
                "next_step_required": True
            }
            
            validated = request_model(**test_request)
            print(f"✅ Request validation successful: {validated.model_dump()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_all_modes():
    """Test schema generation for all mode/complexity combinations"""
    print("\n" + "="*60)
    print("Testing all mode/complexity combinations...")
    print("="*60)
    
    test_cases = [
        ("debug", "simple"),
        ("debug", "workflow"),
        ("review", "simple"),
        ("review", "workflow"),
        ("analyze", "simple"),
        ("consensus", "simple"),
        ("chat", "simple"),
        ("security", "workflow"),
    ]
    
    results = []
    for mode, complexity in test_cases:
        print(f"\nTesting {mode}/{complexity}...")
        try:
            executor = ModeExecutor(mode, complexity)
            schema = executor.get_input_schema()
            json.dumps(schema)  # Test serialization
            print(f"  ✅ {mode}/{complexity} - OK")
            results.append((mode, complexity, True))
        except Exception as e:
            print(f"  ❌ {mode}/{complexity} - FAILED: {e}")
            results.append((mode, complexity, False))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, _, success in results if success)
    total = len(results)
    
    for mode, complexity, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {mode}/{complexity}")
    
    print(f"\nResult: {passed}/{total} tests passed")
    return passed == total

async def main():
    """Run all tests"""
    print("Stage 2 Serialization Fix Test Suite")
    print("="*60)
    
    # Test basic schema generation
    basic_test = await test_schema_generation()
    
    # Test all modes
    all_modes_test = await test_all_modes()
    
    # Final result
    print("\n" + "="*60)
    if basic_test and all_modes_test:
        print("🎉 ALL TESTS PASSED! The fix is working correctly.")
    else:
        print("⚠️  Some tests failed. Please review the errors above.")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())