#!/usr/bin/env python3
# Test what the dashboard HTML actually outputs for the problematic line

html = """    try {
        const o = await fetchJSON('/api/exec?cmd=' + encodeURIComponent(
            "cat /etc/os-release | sed -n 's/PRETTY_NAME=//p' | tr -d '\\\"'"));
        if (o.stdout) document.getElementById('info-os').textContent = o.stdout.trim();
    } catch {}"""

print("=== Python renders this as: ===")
print(html)
print()
# Check for unbalanced quotes
for i, line in enumerate(html.split('\n'), 1):
    print(f"  Line {i}: {repr(line)}")
