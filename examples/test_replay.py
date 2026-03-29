"""Test session recording and replay.

Run:
    python examples/test_replay.py
    bunkervm replay <session-id> --trace
"""

from bunkervm import Sandbox

with Sandbox(record=True) as sb:
    sb.run("x = 42")
    print("Result:", sb.run("print(x * 2)"))

    # Create directory first, then write file
    sb.run("import os; os.makedirs('/tmp/output', exist_ok=True)")
    sb.run("open('/tmp/output/result.txt', 'w').write(str(x))")
    print("File content:", sb.run("print(open('/tmp/output/result.txt').read())"))

    print("\nHistory:")
    for step in sb.history():
        print(f"  Step {step['step']}: {step['command'][:60]}")
