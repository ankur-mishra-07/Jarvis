"""File read/write tools."""

import os
from .registry import tool


@tool("read_file", "Read contents of a file",
      {"path": "File path (absolute or ~/relative)"})
def read_file(path, **kw):
    path = os.path.expanduser(path)
    try:
        with open(path) as f:
            content = f.read()
        if len(content) > 2000:
            return content[:2000] + f"\n... ({len(content)} chars total, truncated)"
        return content or "(empty file)"
    except Exception as e:
        return f"Cannot read: {e}"


@tool("write_file", "Write or append text to a file",
      {"path": "File path", "content": "Text to write", "append": "true/false"})
def write_file(path, content, append="false", **kw):
    path = os.path.expanduser(path)
    mode = "a" if str(append).lower() == "true" else "w"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, mode) as f:
            f.write(content)
        return f"Written to {path}"
    except Exception as e:
        return f"Write error: {e}"


@tool("list_files", "List files in a directory",
      {"path": "Directory path"})
def list_files(path=".", **kw):
    path = os.path.expanduser(path)
    try:
        entries = os.listdir(path)
        dirs = sorted(e + "/" for e in entries if os.path.isdir(os.path.join(path, e)))
        files = sorted(e for e in entries if os.path.isfile(os.path.join(path, e)))
        result = dirs + files
        return "\n".join(result[:50]) if result else "(empty directory)"
    except Exception as e:
        return f"Error: {e}"
