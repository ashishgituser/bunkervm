"""Test secure_agent() API — no external AI deps needed."""
from bunkervm import secure_agent, SecureAgentRuntime

# Test 1: secure_agent() with no agent returns SecureAgentRuntime
print("=== Test 1: secure_agent() returns runtime ===")
runtime = secure_agent()
assert isinstance(runtime, SecureAgentRuntime), f"Expected SecureAgentRuntime, got {type(runtime)}"
print(f"  type: {type(runtime).__name__}")

# Test 2: runtime.run() works (state persists)
r1 = runtime.run("greeting = 'hello secure agent'")
r2 = runtime.run("print(greeting)")
print(f"  run() result: {r2!r}")
assert r2 == "hello secure agent", f"Expected greeting, got {r2!r}"
print("PASS")

# Test 3: runtime.exec() works
r3 = runtime.exec("hostname")
print(f"  hostname: {r3.strip()!r}")
assert "bunkervm" in r3.lower() or len(r3.strip()) > 0
print("PASS")

# Test 4: Cleanup
runtime.stop()
print("  stopped cleanly")
print("PASS")

# Test 5: secure_agent() wrapping a mock agent
print("\n=== Test 2: secure_agent(mock_agent) ===")

class MockAgent:
    def invoke(self, inputs, **kwargs):
        return {"messages": [type("Msg", (), {"content": f"received: {inputs}"})()]}

mock = MockAgent()
safe = secure_agent(mock)
print(f"  type: {type(safe).__name__}")

# The wrapped agent still has .invoke()
result = safe.invoke({"query": "test"})
print(f"  invoke result type: {type(result).__name__}")
assert "messages" in result

# The wrapped agent has .runtime for sandbox access
r = safe.runtime.run("print(2 ** 10)")
print(f"  runtime.run(): {r!r}")
assert r == "1024"

safe.stop()
print("  stopped cleanly")
print("PASS")

print("\nAll secure_agent() tests passed!")
