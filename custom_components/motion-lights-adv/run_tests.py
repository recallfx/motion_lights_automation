#!/usr/bin/env python3
"""Test runner for all motion lights tests."""

import sys
import subprocess
from pathlib import Path

def run_test(test_file, description):
    """Run a single test file."""
    print(f"\n{'=' * 70}")
    print(f"Running: {description}")
    print(f"File: {test_file}")
    print('=' * 70)
    
    result = subprocess.run(
        [sys.executable, test_file],
        capture_output=False,
        text=True
    )
    
    return result.returncode == 0

def main():
    """Run all tests."""
    component_dir = Path(__file__).parent
    
    tests = [
        ("test_modules.py", "Module Unit Tests (State Machine, Timers, etc.)"),
        ("test_functionality.py", "Coordinator Functionality Tests"),
        ("test_logic.py", "Core Logic Tests"),
        ("verify_refactoring.py", "Refactoring Verification"),
    ]
    
    results = {}
    
    print("\n" + "=" * 70)
    print(" MOTION LIGHTS ADVANCED - TEST SUITE")
    print("=" * 70)
    
    for test_file, description in tests:
        test_path = component_dir / test_file
        if test_path.exists():
            success = run_test(str(test_path), description)
            results[description] = success
        else:
            print(f"\n⚠️  Test file not found: {test_file}")
            results[description] = False
    
    # Print summary
    print("\n\n" + "=" * 70)
    print(" TEST SUMMARY")
    print("=" * 70)
    
    all_passed = True
    for description, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status:12} - {description}")
        if not success:
            all_passed = False
    
    print("=" * 70)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! 🎉\n")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
