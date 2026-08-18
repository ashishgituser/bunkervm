# Privacy Policy

**Last updated: 2026-08-18**

BunkerVM is a local command-line tool and MCP server. It has no backend service,
no accounts, and no operator. There is nobody on the other end of it, because
there is no other end.

## What we collect

Nothing. BunkerVM sends no telemetry, analytics, crash reports, or usage
statistics. There is no opt-out because there is nothing to opt out of.

## Data BunkerVM stores, all on your machine

| Path | Contents |
|---|---|
| `~/.bunkervm/logs/audit.jsonl` | Audit log — commands executed in the sandbox and their outcomes |
| `~/.bunkervm/sessions/` | Recorded sessions from `Sandbox(record=True)` — commands, exit codes, stdout/stderr |
| `~/.bunkervm/snapshots/` | Firecracker VM snapshots (memory and disk state) |
| `<project>/.bunkervm/watch/` | `bunkervm watch` recordings — the commands, file edits, and test results from your coding-agent session |

These files never leave your machine. Delete the directory and the data is gone.

Note that `bunkervm watch` records what your coding agent did in a project,
including file paths and command text. If you commit `.bunkervm/` to a shared
repository, you are sharing that history with whoever can read the repository.
Add it to `.gitignore` if that is not what you want.

## Network connections

BunkerVM makes outbound network requests in exactly two situations:

1. **Downloading VM images** — `bunkervm` fetches the kernel and rootfs bundle
   from this project's GitHub Releases (`github.com`) on first run. This is a
   plain file download; no identifying information is sent beyond what any HTTP
   client sends. GitHub's own privacy policy governs what they log.
2. **Talking to the local engine** — the CLI and SDK reach the engine daemon at
   `127.0.0.1:9551`. This is loopback traffic on your own machine.

Code you run *inside* the sandbox may make its own network requests, subject to
the sandbox's network settings. Use `--no-network` to disable sandbox networking.

## The MCP server

`bunkervm server` exposes eight tools over MCP. It is **unauthenticated** and
binds `127.0.0.1` by default, so only processes on your machine can reach it.

Passing `--host 0.0.0.0` makes every tool — including `sandbox_exec` — reachable
by anyone who can route to that address. The VM is isolated from your host; the
port is not isolated from your network. Only widen the bind address on a network
you control.

## Third parties

None. BunkerVM does not integrate any third-party analytics, advertising, or
data-processing service.

## Children

BunkerVM is a developer tool and is not directed at children.

## Changes

Changes to this policy are made in this file and recorded in the repository's
git history. There is no separate notification mechanism because we have no way
to contact you — we do not know who you are.

## Contact

Questions: open an issue at
<https://github.com/ashishgituser/bunkervm/issues>.
