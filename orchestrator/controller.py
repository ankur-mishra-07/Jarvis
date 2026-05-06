"""
J.A.R.V.I.S. Orchestrator — the central brain controller.

Pipeline:
  1. User input arrives (text from STT or typed)
  2. Recall relevant memories from vector store
  3. Send to LLM with tools + memories + system prompt
  4. If LLM returns a tool call → execute tool → feed result back → get final response
  5. If LLM returns a plan → execute each step
  6. Store exchange in memory
  7. Return final response text
"""

import time
import threading
import re
import json

import config


class Orchestrator:
    """
    Central controller that ties together:
      - LLM (reasoning engine)
      - Memory (FAISS vector store)
      - Tools (callable actions)
      - Planner (multi-step decomposition)
    """

    def __init__(self):
        # Lazy-loaded modules (import on first use to keep startup fast)
        self._llm = None
        self._memory = None
        self._tools = None
        self._planner = None
        self._history = []  # short-term: last N messages
        self._MAX_HISTORY = 12

    # ─── Lazy loaders ────────────────────────────────────────────────────

    @property
    def llm(self):
        if self._llm is None:
            from llm.model import LLMRouter
            self._llm = LLMRouter()
        return self._llm

    @property
    def memory(self):
        if self._memory is None:
            from memory import recall, recall_formatted, store, get_stats
            self._memory = type("Mem", (), {
                "recall": staticmethod(recall),
                "recall_formatted": staticmethod(recall_formatted),
                "store": staticmethod(store),
                "get_stats": staticmethod(get_stats),
            })()
        return self._memory

    @property
    def tools(self):
        if self._tools is None:
            from tools_pkg import registry
            self._tools = registry
        return self._tools

    @property
    def planner(self):
        if self._planner is None:
            from planner.planner import Planner
            self._planner = Planner(self)
        return self._planner

    # ─── Main entry point ────────────────────────────────────────────────

    def process(self, user_input: str) -> str:
        """
        Main pipeline: user text in → response text out.
        Handles tool calls, planning, memory, and conversation.
        """
        if not user_input or not user_input.strip():
            return ""

        start = time.time()
        user_input = user_input.strip()

        # 1. Recall relevant memories
        memory_context = ""
        try:
            memory_context = self.memory.recall_formatted(user_input, k=4)
        except Exception as e:
            print(f"  [Memory recall error: {e}]", flush=True)

        # 2. Build messages for LLM
        system_prompt = self._build_system_prompt(memory_context)
        messages = [{"role": "system", "content": system_prompt}]

        # Add short-term history
        for msg in self._history[-self._MAX_HISTORY:]:
            messages.append(msg)

        messages.append({"role": "user", "content": user_input})

        # 3. Call LLM
        response = self.llm.chat(messages)
        if not response:
            return "My thinking engines seem to be offline right now."

        # 4. Check for tool call
        tool_name, tool_args = self._parse_action(response)
        if tool_name:
            print(f"  [Tool: {tool_name}({tool_args})]", flush=True)
            tool_result = self.tools.execute(tool_name, tool_args)
            print(f"  [Result: {str(tool_result)[:120]}]", flush=True)

            # Feed tool result back to LLM for natural response
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content":
                f"[Tool '{tool_name}' returned]: {tool_result}\n"
                "Respond naturally to the user based on this result. Do NOT call another tool."
            })
            response = self.llm.chat(messages) or str(tool_result)

        # 5. Check for plan (multi-step)
        plan_steps = self._parse_plan(response)
        if plan_steps and len(plan_steps) > 1:
            print(f"  [Plan: {len(plan_steps)} steps]", flush=True)
            response = self.planner.execute_plan(plan_steps, messages)

        # 6. Clean up response
        response = self._clean_response(response)

        # 7. Update short-term history
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": response})
        if len(self._history) > self._MAX_HISTORY * 2:
            self._history = self._history[-self._MAX_HISTORY:]

        # 8. Store in long-term memory (async)
        threading.Thread(
            target=self._store_memory,
            args=(user_input, response),
            daemon=True,
        ).start()

        elapsed = time.time() - start
        print(f"  [Orchestrator: {elapsed:.1f}s]", flush=True)
        return response

    # ─── System prompt builder ───────────────────────────────────────────

    def _build_system_prompt(self, memory_context=""):
        owner = config.get("owner_name") or "Boss"
        tool_desc = self.tools.get_descriptions()

        return f"""You are JARVIS, a highly intelligent autonomous AI assistant for {owner}.
You execute tasks, control systems, and respond with precision.

CORE BEHAVIOR:
- Always think step-by-step internally before responding.
- Be precise, structured, and action-oriented.
- Do not give vague answers.
- Keep spoken responses SHORT (1-3 sentences) — they are read aloud via TTS.
- If a task involves execution, use the appropriate tool.

CAPABILITIES:
- You can call tools to take real actions (open apps, search web, read files, etc.)
- You can break complex tasks into a step-by-step plan.
- You remember past conversations and refer to them naturally.

TOOL USAGE:
When you need to take an action, respond with ONLY this JSON (nothing else):
{{"action": "tool_name", "input": {{"param": "value"}}}}

Available tools:
{tool_desc}

IMPORTANT TOOL RULES:
- When calling a tool, output ONLY the JSON. No extra text before or after.
- Only call ONE tool at a time.
- If no tool is needed, respond in plain conversational text.
- NEVER invent tools that aren't listed above.

PLANNING (for complex tasks):
If a task needs multiple steps, output a plan:
{{"plan": ["step 1 description", "step 2 description", ...]}}

{memory_context}

CONSTRAINTS:
- NEVER hallucinate data (weather, calendar, prices). Use tools to fetch real data.
- NEVER roleplay as fictional characters.
- NEVER say 'Done' or 'Opening' unless a tool confirmed the action.
- If you don't know something and no tool can help, say so honestly.

PERSONALITY:
Calm, intelligent, slightly formal British tone (like Iron Man's Jarvis).
Dry wit when appropriate. Minimal fluff. Maximum clarity.
Use {owner}'s name sparingly — once per conversation, not every reply."""

    # ─── Action/tool parsing ─────────────────────────────────────────────

    def _parse_action(self, text):
        """Extract {"action": "name", "input": {...}} from LLM response."""
        # Try direct JSON
        patterns = [
            r'\{\s*"action"\s*:\s*"([^"]+)"\s*,\s*"input"\s*:\s*(\{[^}]*\})\s*\}',
            r'\{\s*"action"\s*:\s*"([^"]+)"\s*,\s*"input"\s*:\s*"([^"]*)"\s*\}',
            r'\{\s*"action"\s*:\s*"([^"]+)"\s*\}',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL)
            if m:
                name = m.group(1)
                if m.lastindex >= 2:
                    raw = m.group(2)
                    try:
                        args = json.loads(raw) if raw.startswith("{") else {"input": raw}
                    except json.JSONDecodeError:
                        args = {"input": raw}
                else:
                    args = {}
                return name, args

        # Also support the old tool_call format for backward compat
        m = re.search(r'\{\s*"tool_call"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"', text)
        if m:
            name = m.group(1)
            args_match = re.search(r'"arguments"\s*:\s*(\{[^}]*\})', text)
            args = {}
            if args_match:
                try:
                    args = json.loads(args_match.group(1))
                except json.JSONDecodeError:
                    pass
            return name, args

        return None, None

    def _parse_plan(self, text):
        """Extract {"plan": ["step1", "step2", ...]} from LLM response."""
        m = re.search(r'\{\s*"plan"\s*:\s*\[([^\]]+)\]\s*\}', text, re.DOTALL)
        if m:
            try:
                items = json.loads("[" + m.group(1) + "]")
                if isinstance(items, list) and len(items) > 1:
                    return items
            except json.JSONDecodeError:
                pass
        return None

    # ─── Response cleanup ────────────────────────────────────────────────

    def _clean_response(self, text):
        """Strip residual JSON, thinking tags, and artifacts."""
        if not text:
            return "Done."
        # Strip <think>...</think>
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Strip tool/action JSON blocks
        text = re.sub(r'\{\s*"action"\s*:.*?\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\{\s*"tool_call"\s*:.*?\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\{\s*"plan"\s*:.*?\}', '', text, flags=re.DOTALL)
        # Strip ```json blocks
        text = re.sub(r'```json\s*\{.*?\}\s*```', '', text, flags=re.DOTALL)
        text = text.strip()
        return text or "Done."

    # ─── Memory storage ──────────────────────────────────────────────────

    def _store_memory(self, user_text, assistant_text):
        try:
            self.memory.store(user_text, assistant_text)
        except Exception as e:
            print(f"  [Memory store error: {e}]", flush=True)
