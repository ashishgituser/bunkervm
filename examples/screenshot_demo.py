#!/usr/bin/env python3
"""
BunkerVM — Time-Travel Debugging Demo
======================================

Rewind an AI sandbox to any previous step.
VM memory, variables, and filesystem all restore instantly.
"""

from bunkervm import Sandbox

with Sandbox(record=True) as sb:
    sb.run("x = 1")
    sb.run("x = x + 10")
    sb.run("x = x * 100")
    print("Before restore:", sb.run("print(x)"))    # → 1100

    sb.restore(2)                                    # ⏪ rewind to step 2
    print("After restore: ", sb.run("print(x)"))    # → 11

    print("\nHistory:")
    for step in sb.history():
        print(f"  Step {step['step']}: {step['command'][:50]}")


# ┌──────────────────────────────────────────────────────────────┐
# │  Expected Output:                                            │
# │                                                              │
# │  Starting sandbox via BunkerVM engine...                     │
# │  Sandbox ready (via engine).                                 │
# │  Before restore: 1100                                        │
# │  Restoring to step 2...                                      │
# │  Restored to step 2. Sandbox ready.                          │
# │  After restore:  11                                          │
# │                                                              │
# │  History:                                                    │
# │    Step 1: x = 1                                             │
# │    Step 2: x = x + 10                                        │
# │    Step 3: print(x)                                          │
# │  Session saved to .bunkervm/sessions/fcaff77c5fd9.json       │
# │  Destroying sandbox...                                       │
# │  Done.                                                       │
# └──────────────────────────────────────────────────────────────┘
