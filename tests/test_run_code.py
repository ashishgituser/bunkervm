"""Test run_code() Python API directly."""
from bunkervm import run_code

# Test 1: Simple expression
print("=== Test 1: Simple print ===")
result = run_code("print('Hello from run_code!')")
print(f"Result: {result!r}")
assert "Hello from run_code!" in result, f"Expected greeting in output, got: {result}"
print("PASS\n")

# Test 2: Multi-line computation
print("=== Test 2: Multi-line code ===")
code = """
import math
for i in range(5):
    print(f"{i}: {math.factorial(i)}")
"""
result = run_code(code)
print(f"Result: {result!r}")
assert "4: 24" in result, f"Expected '4: 24' in output, got: {result}"
print("PASS\n")

# Test 3: Timeout parameter
print("=== Test 3: With explicit timeout ===")
result = run_code("print(sum(range(100)))", timeout=15)
print(f"Result: {result!r}")
assert "4950" in result, f"Expected 4950, got: {result}"
print("PASS\n")

print("All run_code() tests passed!")
