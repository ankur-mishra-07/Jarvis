"""
J.A.R.V.I.S. Tool Registry
Central registry that auto-discovers and manages all tools.

Each tool module in tools_pkg/ registers itself via the @tool decorator.
The orchestrator calls execute(name, args) and get_descriptions().
"""

import json

# Global tool registry: name → {description, parameters, handler}
_TOOLS = {}


def tool(name, description, params=None):
    """Decorator to register a tool."""
    def decorator(fn):
        _TOOLS[name] = {
            "name": name,
            "description": description,
            "parameters": params or {},
            "handler": fn,
        }
        return fn
    return decorator


def execute(name, arguments):
    """Execute a tool by name. Handles flexible argument mapping."""
    if name not in _TOOLS:
        available = ", ".join(_TOOLS.keys())
        return f"Unknown tool: {name}. Available: {available}"

    tool_def = _TOOLS[name]
    handler = tool_def["handler"]

    # Normalize arguments
    if isinstance(arguments, str):
        # Model sent a plain string instead of dict
        expected = list(tool_def["parameters"].keys())
        arguments = {expected[0]: arguments} if expected else {"input": arguments}

    # Flexible argument mapping: "input"/"param"/"value" → first expected param
    if arguments and tool_def["parameters"]:
        expected_keys = list(tool_def["parameters"].keys())
        generic = {"input", "param", "value", "arg", "text", "query"}
        for gk in generic:
            if gk in arguments and gk not in expected_keys and expected_keys:
                arguments[expected_keys[0]] = arguments.pop(gk)

    try:
        result = handler(**arguments)
        return str(result)
    except Exception as e:
        return f"Tool error ({name}): {e}"


def get_descriptions():
    """Generate tool descriptions for the system prompt."""
    lines = []
    for name, t in _TOOLS.items():
        params = ""
        if t["parameters"]:
            params = ", ".join(f'{k}' for k in t["parameters"].keys())
        lines.append(f'  - {name}({params}): {t["description"]}')
    return "\n".join(lines)


def list_tools():
    """Return list of tool names."""
    return list(_TOOLS.keys())


# ─── Auto-import all tool modules ────────────────────────────────────────────
# This triggers the @tool decorators in each module.

from . import shell, file_ops, apps, web, system, media, productivity
