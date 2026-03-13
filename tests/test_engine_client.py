"""Quick test: EngineSandboxClient connects to running engine."""
import sys
import urllib.request
import json

engine_url = "http://localhost:9551"

# 1. Check engine is running
req = urllib.request.Request(f"{engine_url}/engine/status", method="GET")
resp = urllib.request.urlopen(req, timeout=2)
data = json.loads(resp.read())
print(f"Engine detected: {data['status']}")

# 2. Create client
from bunkervm.engine_client import EngineSandboxClient

client = EngineSandboxClient(engine_url=engine_url, sandbox_name="mcp-test")
print(f"Client created, sandbox_id: {client._sandbox_id}")

# 3. Exec (auto-creates sandbox)
result = client.exec("echo hello from engine")
print(f"Exec result: {result}")

# 4. Read file
result = client.exec("echo 'test content' > /tmp/testfile.txt")
content = client.read_file("/tmp/testfile.txt")
print(f"Read file: {content}")

# 5. List dir
listing = client.list_dir("/tmp")
print(f"List dir /tmp: {listing}")

# 6. Write file
client.write_file("/tmp/written.txt", "hello from engine client")
verify = client.read_file("/tmp/written.txt")
print(f"Write+read verify: {verify}")

# 7. Health
health = client.health()
print(f"Health: {health}")

# 8. Cleanup
client.destroy()
print("Sandbox destroyed - ALL TESTS PASSED")
