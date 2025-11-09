#!/usr/bin/env python3
"""
Comprehensive Testing Script for Zen CLI
Tests all tools with various file scenarios to ensure they work as expected
"""

import json
import subprocess
import sys
from pathlib import Path

# Test configuration
TEST_MODEL = "gemini-flash"
SCRIPT_DIR = Path(__file__).parent
TEST_FILE = SCRIPT_DIR / "README.md"
TEST_FILE2 = SCRIPT_DIR / "setup.py"
NON_EXISTENT_FILE = SCRIPT_DIR / "nonexistent.txt"


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def run_command(cmd, expected_success=True):
    """Run a zen command and check if it succeeds."""
    print(f"{Colors.CYAN}Running: {' '.join(cmd)}{Colors.RESET}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # Check if command succeeded
        success = result.returncode == 0

        # Try to parse JSON output if available
        output = result.stdout
        try:
            json_output = json.loads(output)
            # Check for files_required_to_continue status
            if json_output.get("status") == "files_required_to_continue":
                success = False
                print(f"  {Colors.YELLOW}⚠ Tool requested files but didn't receive them{Colors.RESET}")
        except json.JSONDecodeError:
            pass  # Not JSON output, which is fine

        if success == expected_success:
            print(f"  {Colors.GREEN}✓ Pass{Colors.RESET}")
            return True
        else:
            print(f"  {Colors.RED}✗ Fail{Colors.RESET}")
            if result.stderr:
                print(f"  {Colors.RED}Error: {result.stderr[:200]}{Colors.RESET}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  {Colors.RED}✗ Timeout{Colors.RESET}")
        return False
    except Exception as e:
        print(f"  {Colors.RED}✗ Exception: {e}{Colors.RESET}")
        return False


def test_basic_commands():
    """Test basic commands that don't need files."""
    print(f"\n{Colors.BOLD}=== Testing Basic Commands ==={Colors.RESET}")

    tests = [
        (["zen", "--version"], "Version check"),
        (["zen", "listmodels"], "List models"),
        (["zen", "chat", "Say hello", "--model", TEST_MODEL, "--json"], "Chat without files"),
    ]

    results = []
    for cmd, description in tests:
        print(f"\n{description}:")
        results.append(run_command(cmd))

    return all(results)


def test_file_handling():
    """Test commands with file handling."""
    print(f"\n{Colors.BOLD}=== Testing File Handling ==={Colors.RESET}")

    # Create test files if they don't exist
    if not TEST_FILE.exists():
        print(f"{Colors.YELLOW}Creating test file: {TEST_FILE}{Colors.RESET}")
        TEST_FILE.write_text("# Test README\n\nThis is a test file for zen CLI testing.")

    tests = [
        # Test with single file
        (
            ["zen", "debug", "Test issue", "-f", str(TEST_FILE), "--model", TEST_MODEL, "--json"],
            "Debug with single file",
        ),
        # Test with multiple files using repeated -f
        (
            [
                "zen",
                "debug",
                "Test issue",
                "-f",
                str(TEST_FILE),
                "-f",
                str(TEST_FILE2),
                "--model",
                TEST_MODEL,
                "--json",
            ],
            "Debug with multiple files (repeated -f)",
        ),
        # Test with comma-separated files
        (
            ["zen", "debug", "Test issue", "-f", f"{TEST_FILE},{TEST_FILE2}", "--model", TEST_MODEL, "--json"],
            "Debug with comma-separated files",
        ),
        # Test with absolute path
        (
            ["zen", "debug", "Test issue", "-f", str(TEST_FILE.absolute()), "--model", TEST_MODEL, "--json"],
            "Debug with absolute path",
        ),
        # Test codereview with files
        (
            ["zen", "codereview", "-f", str(TEST_FILE), "--review-type", "quality", "--model", TEST_MODEL, "--json"],
            "Codereview with file",
        ),
        # Test analyze with files
        (
            ["zen", "analyze", "-f", str(TEST_FILE), "--analysis-type", "all", "--model", TEST_MODEL, "--json"],
            "Analyze with file",
        ),
        # Test consensus with context files
        (
            ["zen", "consensus", "Is this good documentation?", "-f", str(TEST_FILE), "--model", TEST_MODEL, "--json"],
            "Consensus with context file",
        ),
        # Test planner with context files
        (
            ["zen", "planner", "Improve this documentation", "-f", str(TEST_FILE), "--model", TEST_MODEL, "--json"],
            "Planner with context file",
        ),
        # Test chat with files
        (
            ["zen", "chat", "What is this file about?", "-f", str(TEST_FILE), "--model", TEST_MODEL, "--json"],
            "Chat with file",
        ),
    ]

    results = []
    for cmd, description in tests:
        print(f"\n{description}:")
        results.append(run_command(cmd))

    return all(results)


def test_workflow_without_files():
    """Test workflow tools without providing files."""
    print(f"\n{Colors.BOLD}=== Testing Workflow Tools Without Files ==={Colors.RESET}")

    tests = [
        (
            ["zen", "debug", "Generic issue", "--model", TEST_MODEL, "--json"],
            "Debug without files (should investigate, not demand files)",
        ),
        (
            ["zen", "codereview", "--review-type", "quality", "--model", TEST_MODEL, "--json"],
            "Codereview without files (should offer to find files)",
        ),
        (
            ["zen", "analyze", "--analysis-type", "architecture", "--model", TEST_MODEL, "--json"],
            "Analyze without files (should explore codebase)",
        ),
    ]

    results = []
    for cmd, description in tests:
        print(f"\n{description}:")
        results.append(run_command(cmd))

    return all(results)


def test_error_handling():
    """Test error handling scenarios."""
    print(f"\n{Colors.BOLD}=== Testing Error Handling ==={Colors.RESET}")

    tests = [
        # Non-existent file
        (
            ["zen", "debug", "Test issue", "-f", str(NON_EXISTENT_FILE), "--model", TEST_MODEL, "--json"],
            "Debug with non-existent file",
            False,
        ),  # Should fail gracefully
        # Invalid model
        (
            ["zen", "chat", "Hello", "--model", "invalid-model", "--json"],
            "Chat with invalid model",
            False,
        ),  # Should fail
    ]

    results = []
    for cmd, description, expected in tests:
        print(f"\n{description}:")
        results.append(run_command(cmd, expected_success=expected))

    return all(results)


def main():
    """Run all tests and report results."""
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Zen CLI Comprehensive Test Suite{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")

    # Check if zen is available
    print(f"\n{Colors.CYAN}Checking zen CLI availability...{Colors.RESET}")
    if not run_command(["zen", "--version"]):
        print(f"{Colors.RED}zen CLI not found! Please install it first.{Colors.RESET}")
        sys.exit(1)

    # Run test suites
    test_results = {
        "Basic Commands": test_basic_commands(),
        "File Handling": test_file_handling(),
        "Workflow Without Files": test_workflow_without_files(),
        "Error Handling": test_error_handling(),
    }

    # Print summary
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")

    total_passed = sum(test_results.values())
    total_tests = len(test_results)

    for suite, passed in test_results.items():
        if passed:
            print(f"{Colors.GREEN}✓ {suite}: PASSED{Colors.RESET}")
        else:
            print(f"{Colors.RED}✗ {suite}: FAILED{Colors.RESET}")

    print(f"\n{Colors.BOLD}Overall: {total_passed}/{total_tests} test suites passed{Colors.RESET}")

    if total_passed == total_tests:
        print(f"{Colors.GREEN}{Colors.BOLD}All tests passed! 🎉{Colors.RESET}")
        sys.exit(0)
    else:
        print(f"{Colors.RED}{Colors.BOLD}Some tests failed. Please review the output above.{Colors.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
