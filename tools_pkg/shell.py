"""Shell command execution tool."""

import subprocess
from .registry import tool


@tool("run_shell", "Run a shell command and return output",
      {"command": "The shell command to execute"})
def run_shell(command, **kw):
    blocked = ("rm -rf /", "sudo rm", "mkfs", "dd if=", "> /dev/",
               "format c:", "diskutil erase")
    if any(b in command.lower() for b in blocked):
        return "Blocked: that command could be destructive."
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        return output[:800] if output else "(command completed, no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except Exception as e:
        return f"Error: {e}"
