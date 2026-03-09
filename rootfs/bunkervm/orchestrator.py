#!/usr/bin/env python3
"""
BunkerVM Orchestrator — Dynamic AI-native OS agent.

Architecture:
  llama-server (:8080)  <-->  orchestrator.py  <-->  shell (any command)

The model decides what commands to run. No hardcoded tools.
The entire OS is the tool — any command available on the system works.

Flow:
  1. User types request
  2. Model outputs JSON: either {"cmd":"..."} to run a command,
     or {"reply":"..."} to respond to the user
  3. If cmd: execute it, feed output back, model summarizes
  4. If reply: print and wait for next input
"""

import json
import sys
import os
import time
import urllib.request
import urllib.error

BUNKERVM_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BUNKERVM_DIR)

from tools import execute

# Configuration
LLAMA_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080")
SYSTEM_PROMPT_FILE = os.path.join(BUNKERVM_DIR, "system_prompt.txt")

# Colors
C_RESET = "\033[0m"
C_GREEN = "\033[32m"
C_CYAN = "\033[36m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"


def load_system_prompt() -> str:
    with open(SYSTEM_PROMPT_FILE, "r") as f:
        return f.read().strip()


def llm_chat(messages: list) -> str:
    """Send chat request, return raw content string."""
    payload = {
        "messages": messages,
        "temperature": 0.1,
        "top_p": 0.9,
        "max_tokens": 300,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{LLAMA_URL}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return json.dumps({"reply": f"[error: {e}]"})


def parse_response(raw: str) -> dict:
    """Parse model output. Extract cmd or reply."""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Not valid JSON — treat the whole thing as a reply
    return {"reply": raw}


def wait_for_server(timeout: int = 300) -> bool:
    """Wait for llama-server health check."""
    start = time.time()
    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        try:
            req = urllib.request.Request(f"{LLAMA_URL}/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                status = body.get("status", "")
                if status == "ok":
                    return True
                elif status == "loading model":
                    sys.stdout.write(
                        f"\r  {C_YELLOW}Loading model... ({elapsed}s){C_RESET}    "
                    )
                    sys.stdout.flush()
        except Exception:
            if elapsed > 2:
                sys.stdout.write(
                    f"\r  {C_YELLOW}Starting engine... ({elapsed}s){C_RESET}    "
                )
                sys.stdout.flush()
        time.sleep(1)
    return False


def print_banner():
    print(
        f"""
{C_CYAN}{C_BOLD}
  ███╗   ██╗███████╗██████╗ ██╗   ██╗ ██████╗ ███████╗
  ████╗  ██║██╔════╝██╔══██╗██║   ██║██╔═══██╗██╔════╝
  ██╔██╗ ██║█████╗  ██████╔╝██║   ██║██║   ██║███████╗
  ██║╚██╗██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██║   ██║╚════██║
  ██║ ╚████║███████╗██║  ██║ ╚████╔╝ ╚██████╔╝███████║
  ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝  ╚═══╝   ╚═════╝ ╚══════╝
{C_RESET}
  {C_DIM}AI-Native Operating System • Firecracker MicroVM{C_RESET}
  {C_DIM}Model: Qwen 2.5 0.5B • Engine: llama.cpp{C_RESET}
"""
    )


def run_agent_loop():
    """Main agent REPL."""
    system_prompt = load_system_prompt()

    print_banner()

    # Wait for inference engine
    print(f"  {C_YELLOW}Waiting for inference engine...{C_RESET}")
    if wait_for_server():
        print(f"\r  {C_GREEN}✓ Inference engine ready.{C_RESET}                    ")
    else:
        print(f"\r  {C_RED}✗ Engine timeout!{C_RESET}                             ")
        print(f"  {C_RED}Check /var/log/llama-server.log{C_RESET}")
        return

    # Boot time
    try:
        with open("/proc/uptime") as f:
            uptime = float(f.read().split()[0])
        print(f"  {C_GREEN}⚡ Boot-to-ready: {uptime:.1f}s{C_RESET}")
    except Exception:
        pass

    print()
    print(f"  {C_DIM}Ask me anything. I am the operating system.{C_RESET}")
    print(f"  {C_DIM}Type 'exit' to shut down.{C_RESET}")
    print()

    # Few-shot examples: teach the two-step pattern
    #   user asks → model outputs {"cmd":"..."} → we run it → we feed output →
    #   model outputs {"reply":"..."} with summary
    few_shot = [
        {"role": "user", "content": "what cpu do i have?"},
        {"role": "assistant", "content": '{"cmd":"cat /proc/cpuinfo | grep model\\\\ name | head -1"}'},
        {"role": "user", "content": '[output]\nmodel name\t: AMD EPYC 9R14\n[/output]\nNow summarize the result for the user as {"reply":"..."}'},
        {"role": "assistant", "content": '{"reply":"You have an AMD EPYC 9R14 processor."}'},
        {"role": "user", "content": "how much ram?"},
        {"role": "assistant", "content": '{"cmd":"free -h | head -2"}'},
        {"role": "user", "content": '[output]\n              total        used        free\nMem:          2.0Gi       120Mi       1.8Gi\n[/output]\nNow summarize the result for the user as {"reply":"..."}'},
        {"role": "assistant", "content": '{"reply":"You have 2GB RAM total, 1.8GB free."}'},
        {"role": "user", "content": "list files in /"},
        {"role": "assistant", "content": '{"cmd":"ls -la /"}'},
        {"role": "user", "content": '[output]\ntotal 68\ndrwxr-xr-x  18 root root  4096 Mar  1 bunkervm\ndrwxr-xr-x   2 root root  4096 Mar  1 bin\ndrwxr-xr-x   3 root root  4096 Mar  1 etc\n[/output]\nNow summarize the result for the user as {"reply":"..."}'},
        {"role": "assistant", "content": '{"reply":"Root directory contains: bunkervm/, bin/, etc/ and more."}'},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": '{"reply":"Hello! I am BunkerVM, your AI operating system. Ask me to check hardware, run commands, manage files, or anything else."}'},
    ]

    messages = [{"role": "system", "content": system_prompt}] + few_shot

    while True:
        try:
            user_input = input(f"{C_GREEN}bunkervm>{C_RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C_YELLOW}Shutting down BunkerVM...{C_RESET}")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "shutdown", "poweroff"):
            print(f"{C_YELLOW}BunkerVM shutting down...{C_RESET}")
            break

        messages.append({"role": "user", "content": user_input})

        # Step 1: Ask model what to do
        raw = llm_chat(messages)
        parsed = parse_response(raw)

        if "cmd" in parsed:
            # Model wants to run a command
            cmd = parsed["cmd"]
            print(f"  {C_DIM}$ {cmd}{C_RESET}")

            result = execute(cmd)
            out = result.get("out", result.get("err", ""))
            if not out and not result["ok"]:
                out = result.get("error", "command produced no output")

            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f'[output]\n{out[:2048]}\n[/output]\nNow summarize the result for the user as {{"reply":"..."}}',
            })

            # Step 2: Model summarizes
            raw2 = llm_chat(messages)
            parsed2 = parse_response(raw2)
            reply = parsed2.get("reply", out[:500])
            print(f"  {C_CYAN}{reply}{C_RESET}")
            messages.append({"role": "assistant", "content": raw2})

        elif "reply" in parsed:
            # Model responds directly
            print(f"  {C_CYAN}{parsed['reply']}{C_RESET}")
            messages.append({"role": "assistant", "content": raw})

        else:
            # Unknown format — print whatever we got
            print(f"  {C_CYAN}{raw[:500]}{C_RESET}")
            messages.append({"role": "assistant", "content": raw})

        # Keep context manageable: system + few-shot + last 8 conversation msgs
        fs_end = 1 + len(few_shot)
        if len(messages) > fs_end + 8:
            messages = messages[:fs_end] + messages[-8:]

        print()


if __name__ == "__main__":
    run_agent_loop()
