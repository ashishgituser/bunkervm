#!/bin/bash
# Record the FULL BunkerVM user journey as a GIF
#
# Prerequisites:
#   - Clean Ubuntu (no bunkervm installed)
#   - .env with OPENAI_API_KEY at ~/.env
#   - asciinema installed: sudo apt install asciinema
#   - agg at /tmp/agg
#
# Usage: bash record_demo.sh

set -e

CAST_FILE="$HOME/bunkervm-demo.cast"
GIF_FILE="/mnt/c/ashish/NervOS/docs/demo.gif"
DEMO_SCRIPT="$HOME/bunkervm-full-demo.sh"

# Create the demo script that asciinema will record
cat > "$DEMO_SCRIPT" << 'DEMO'
#!/bin/bash
set -e

# Colors
CYAN='\033[1;36m'
YELLOW='\033[1;33m'
GREEN='\033[1;32m'
RESET='\033[0m'

step() { echo -e "\n${YELLOW}━━━ $1 ━━━${RESET}\n"; sleep 1; }
ok()   { echo -e "${GREEN}  ✓ $1${RESET}"; }

echo -e "${CYAN}"
echo "  ╔════════════════════════════════════════════════╗"
echo "  ║  🔒 BunkerVM — Full Demo                      ║"
echo "  ║  Hardware-isolated AI sandbox from PyPI        ║"
echo "  ╚════════════════════════════════════════════════╝"
echo -e "${RESET}"
sleep 2

# ── Cleanup: start from scratch ──
step "Step 0: Clean slate"
echo "  Stopping any running VMs..."
sudo pkill -f "python3 -m bunkervm" 2>/dev/null || true
sudo pkill firecracker 2>/dev/null || true
sleep 2
sudo rm -f /tmp/bunkervm-vsock.sock /tmp/bunkervm-api.sock
sudo rm -rf /root/.bunkervm 2>/dev/null || true
pip uninstall bunkervm -y 2>/dev/null || true
ok "Clean slate"
sleep 1

# ── Step 1: Install ──
step "Step 1: Install from PyPI"
echo "$ pip install bunkervm[langgraph]"
pip install bunkervm[langgraph] 2>&1 | tail -5
ok "bunkervm installed"
sleep 1

# Show version
echo ""
echo "$ python3 -c \"import bunkervm; print(bunkervm.__version__)\""
python3 -c "import bunkervm; print(bunkervm.__version__)"
sleep 1

# ── Step 2: Start VM ──
step "Step 2: Start BunkerVM (Firecracker MicroVM)"

# Kill any existing VM first
sudo pkill -f "python3 -m bunkervm" 2>/dev/null || true
sudo pkill firecracker 2>/dev/null || true
sleep 2
sudo rm -f /tmp/bunkervm-vsock.sock /tmp/bunkervm-api.sock

echo "$ sudo python3 -m bunkervm &"
# Use SSE transport so the server doesn't exit when stdin closes (backgrounded)
sudo $(which python3) -m bunkervm --transport sse 2>&1 &
VM_PID=$!

# Wait for VM to be ready — check socket exists AND agent responds
echo ""
echo "  Waiting for VM to boot..."
READY=false
for i in $(seq 1 90); do
    if sudo test -S /tmp/bunkervm-vsock.sock; then
        # Socket exists, try a health check
        if sudo $(which python3) -c "
from bunkervm import SandboxClient
c = SandboxClient()
h = c.health()
exit(0 if h.get('status') == 'ok' else 1)
" 2>/dev/null; then
            READY=true
            ok "VM booted! (Firecracker MicroVM with KVM isolation)"
            break
        fi
    fi
    sleep 1
done

if [ "$READY" = false ]; then
    echo "  ✗ VM failed to start"
    exit 1
fi
sleep 1

# ── Step 3: Quick smoke test ──
step "Step 3: Verify — run commands inside the VM"
echo '$ python3 -c "from bunkervm import SandboxClient; c = SandboxClient(); print(c.exec(\"uname -a\")[\"stdout\"])"'
sudo $(which python3) -c "
from bunkervm import SandboxClient
c = SandboxClient()
r = c.exec('uname -a')
print(r['stdout'].strip())
"
ok "Commands execute inside isolated VM"
sleep 1

# ── Step 4: LangGraph Agent ──
step "Step 4: AI Agent writes & runs code in the VM"

sudo $(which python3) -c "
import logging, os
logging.basicConfig(level=logging.INFO, format='  %(message)s')
for name in ['httpx', 'httpcore', 'openai']:
    logging.getLogger(name).setLevel(logging.WARNING)

from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.env'))

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from bunkervm.langchain import BunkerVMToolkit

toolkit = BunkerVMToolkit()
agent = create_react_agent(ChatOpenAI(model='gpt-4o', temperature=0), toolkit.get_tools())

task = 'Write a Python script that finds prime numbers under 50, save it to /tmp/primes.py, run it, show results.'
print(f'\n  Task: \"{task}\"\n')

result = agent.invoke({'messages': [('human', task)]})

for msg in result['messages']:
    if hasattr(msg, 'tool_calls') and msg.tool_calls:
        for tc in msg.tool_calls:
            args = tc['args']
            detail = args.get('command', args.get('path', ''))
            print(f'  ⚡ {tc[\"name\"]} → {detail}')
    elif msg.type == 'tool':
        content = msg.content.strip()
        if content and content != '(no output)':
            for line in content.split(chr(10))[:5]:
                print(f'     {line}')
    elif msg.type == 'ai' and msg.content:
        print(f'\n  🤖 {msg.content[:200]}')
"
sleep 1

# ── Step 5: Prove isolation ──
step "Step 5: Prove it's isolated (VM ≠ Host)"
sudo $(which python3) -c "
import platform
from bunkervm import SandboxClient
c = SandboxClient()

host_h = platform.node()
vm_h = c.exec('hostname')['stdout'].strip()
host_k = platform.release()[:20]
vm_k = c.exec('uname -r')['stdout'].strip()
host_os = 'Ubuntu (WSL2)'
vm_os = c.exec('cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2')['stdout'].strip().strip('\"')

print(f'  {\"\":>10} {\"HOST\":>18}  {\"VM (Firecracker)\":>20}')
print(f'  {\"Hostname:\":>10} {host_h:>18}  {vm_h:>20}')
print(f'  {\"Kernel:\":>10} {host_k:>18}  {vm_k:>20}')
print(f'  {\"OS:\":>10} {host_os:>18}  {vm_os:>20}')
"
sleep 2

echo -e "\n${GREEN}  ✅ BunkerVM — Hardware-isolated AI sandbox. pip install bunkervm${RESET}\n"
sleep 3

# Cleanup
sudo kill $VM_PID 2>/dev/null || true
DEMO

chmod +x "$DEMO_SCRIPT"

echo "🎬 Starting recording..."
echo "   This will run the full demo automatically."
echo ""

# Record
asciinema rec "$CAST_FILE" \
  --cols 90 \
  --rows 28 \
  --title "BunkerVM — AI Agent Sandbox Demo" \
  --command "bash $DEMO_SCRIPT" \
  --overwrite

echo ""
echo "🎞  Converting to GIF..."

/tmp/agg "$CAST_FILE" "$GIF_FILE" \
  --theme dracula \
  --font-size 14 \
  --speed 1.5 \
  --cols 90 \
  --rows 28

echo ""
echo "✅ GIF saved to: $GIF_FILE"
echo "   Size: $(du -h "$GIF_FILE" | cut -f1)"
echo "   Cast: $CAST_FILE"
