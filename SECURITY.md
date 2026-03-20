# Security Policy

## BunkerVM Security Model

BunkerVM provides **hardware-level isolation** using [Firecracker](https://firecracker-microvm.github.io/) microVMs (the same technology that powers AWS Lambda and AWS Fargate). Each sandbox runs in its own virtual machine with:

- **Separate kernel** — the guest Linux kernel is completely independent from the host
- **KVM isolation** — enforced by the CPU's hardware virtualization extensions
- **Minimal attack surface** — Firecracker exposes ~30 syscalls to the host (vs ~400+ for containers)
- **Ephemeral by design** — VMs are destroyed after use, leaving no persistent state

### Isolation Guarantees

| Layer | BunkerVM | Docker |
|---|---|---|
| Kernel | Separate (own kernel) | Shared with host |
| Syscall surface | ~30 (Firecracker) | ~400+ (seccomp default) |
| Hardware isolation | KVM (CPU-enforced) | Namespaces (kernel-enforced) |
| Escape complexity | Requires KVM + Firecracker exploit | Namespace/cgroup escape |

### What BunkerVM Protects Against

- ✅ Malicious code execution (file deletion, data exfiltration, crypto mining)
- ✅ Supply chain attacks in AI-generated code
- ✅ Resource abuse (CPU/memory limits enforced by Firecracker)
- ✅ Network-based attacks (VM networking is off by default)
- ✅ Persistent compromise (VM is destroyed after each use)

### What BunkerVM Does NOT Protect Against

- ❌ Side-channel attacks against the CPU (Spectre/Meltdown class) — mitigated by CPU microcode updates
- ❌ Vulnerabilities in the host kernel's KVM implementation — extremely rare but theoretically possible
- ❌ Social engineering through LLM output displayed to the user — BunkerVM isolates execution, not output

### Safety Classifier

BunkerVM includes an advisory command classifier (`safety.py`) that categorizes commands as READ/WRITE/SYSTEM/DESTRUCTIVE/BLOCKED. This is **defense-in-depth only** — the VM is the real isolation boundary. Even "destructive" commands like `rm -rf /` are safe inside the VM.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.8.x   | ✅ Current |
| < 0.8   | ❌ Upgrade recommended |

## Reporting a Vulnerability

If you discover a security vulnerability in BunkerVM, please report it responsibly:

1. **Email:** Send details to the maintainer via GitHub (open a private security advisory)
2. **GitHub:** Use [GitHub Security Advisories](https://github.com/ashishgituser/bunkervm/security/advisories/new)
3. **Do NOT** open a public issue for security vulnerabilities

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix release:** As soon as possible, depending on severity

## Dependencies

BunkerVM has minimal dependencies by design:

- **Core:** Only `mcp` (Model Context Protocol SDK)
- **Guest code:** Zero dependencies (stdlib-only Python)
- **Firecracker:** Downloaded as a static binary from official releases

This minimal dependency tree significantly reduces supply chain attack surface.
