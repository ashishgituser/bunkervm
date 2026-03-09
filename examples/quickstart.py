#!/usr/bin/env python3
"""
BunkerVM Quick Examples — Copy-paste ready.

No API keys needed. Just BunkerVM.
"""

# ── Example 1: One-liner ──

from bunkervm import run_code

result = run_code("print('Hello from BunkerVM!')")
print(result)  # Hello from BunkerVM!


# ── Example 2: Multi-line code ──

result = run_code("""
import math
primes = [n for n in range(2, 50) if all(n % i for i in range(2, int(math.sqrt(n))+1))]
print(f"Primes under 50: {primes}")
print(f"Count: {len(primes)}")
""")
print(result)


# ── Example 3: Reusable sandbox ──

from bunkervm import Sandbox

with Sandbox() as sb:
    sb.run("x = 42")
    sb.run("y = x * 2")
    result = sb.run("print(f'x={x}, y={y}')")
    print(result)  # x=42, y=84


# ── Example 4: File operations ──

from bunkervm import Sandbox

with Sandbox() as sb:
    # Write a file inside the VM
    sb.run("""
with open('/tmp/data.csv', 'w') as f:
    f.write('name,age\\n')
    f.write('Alice,30\\n')
    f.write('Bob,25\\n')
    """)

    # Read it back
    result = sb.run("""
with open('/tmp/data.csv') as f:
    print(f.read())
    """)
    print(result)

    # Download to host
    data = sb.download("/tmp/data.csv")
    print(f"Downloaded {len(data)} bytes")


# ── Example 5: Secure agent (requires OPENAI_API_KEY) ──
#
# from bunkervm import secure_agent
# runtime = secure_agent()
# result = runtime.run("print('AI code runs safely here')")
# print(result)
# runtime.stop()
