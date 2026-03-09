# BunkerVM Demo — VHS Tape
# Records a polished GIF of BunkerVM in action.
#
# Prerequisites:
#   1. Install VHS: go install github.com/charmbracelet/vhs@latest
#   2. VM must be running: sudo python3 -m bunkervm
#   3. Venv active with bunkervm[langgraph] installed
#   4. .env with OPENAI_API_KEY in home dir
#
# Record: vhs demo.tape
# Output: demo.gif

Output demo.gif

# GIF settings
Set Theme "Dracula"
Set FontSize 14
Set Width 900
Set Height 500
Set Padding 15
Set TypingSpeed 40ms
Set PlaybackSpeed 1

# ── Show what we're doing ──
Type "# 🔒 BunkerVM — AI agent sandbox powered by Firecracker MicroVM"
Enter
Sleep 1.5s

Type "# Step 1: Install from PyPI"
Enter
Sleep 500ms
Type "pip install bunkervm[langgraph]"
Enter
Sleep 3s

# ── Run the demo ──
Type "# Step 2: Run the demo (VM already running in background)"
Enter
Sleep 500ms
Type "sudo $(which python3) examples/demo.py"
Enter

# Wait for the full demo to complete (agent + OpenAI calls)
Sleep 25s

# Let viewer read the output
Sleep 5s
