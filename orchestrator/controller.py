"""
J.A.R.V.I.S. Orchestrator — the central brain controller.

Optimized for voice: fast responses (< 3s target).
Tool calls and web search are handled by commands.py BEFORE reaching here.
The Orchestrator is purely for conversational AI responses.

Pipeline:
  1. User input arrives (text that didn't match any command trigger)
  2. Recall relevant memories (cached, non-blocking on first load)
  3. Send to LLM with compact system prompt + memories
  4. Return response text (no tool call parsing — that's commands.py's job)
"""

import time
import threading
import re
import json

import config


class Orchestrator:
    """
    Conversational brain controller.
    Kept lean for fast voice responses — no tool calls, no planning.
    Tools/search/actions are handled in commands.py before reaching here.
    """

    def __init__(self):
        self._llm = None
        self._memory = None
        self._memory_ready = False
        self._history = []
        self._MAX_HISTORY = 6  # Short-term: last 6 messages (3 turns)

        # Pre-warm memory loading in background
        threading.Thread(target=self._warmup_memory, daemon=True).start()

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
            try:
                from memory import recall, recall_formatted, store, get_stats
                self._memory = type("Mem", (), {
                    "recall": staticmethod(recall),
                    "recall_formatted": staticmethod(recall_formatted),
                    "store": staticmethod(store),
                    "get_stats": staticmethod(get_stats),
                })()
                self._memory_ready = True
            except Exception as e:
                print(f"  [Memory unavailable: {e}]", flush=True)
                self._memory = None
        return self._memory

    def _warmup_memory(self):
        """Pre-load embedding model in background so first query isn't slow."""
        try:
            _ = self.memory
            if self._memory:
                self._memory.get_stats()
                self._memory_ready = True
        except Exception:
            pass

    # ─── Main entry point ────────────────────────────────────────────────

    def process(self, user_input: str) -> str:
        """
        Conversational pipeline: user text in → response text out.
        Optimized for speed — no tool calls, no planning.
        Target: < 3s on local Ollama.
        """
        if not user_input or not user_input.strip():
            return ""

        start = time.time()
        user_input = user_input.strip()

        # 1. Recall relevant memories (skip if memory not ready yet)
        memory_context = ""
        if self._memory_ready and self._memory:
            try:
                memory_context = self._memory.recall_formatted(user_input, k=3)
            except Exception as e:
                print(f"  [Memory recall error: {e}]", flush=True)

        # 2. Build compact messages for LLM
        system_prompt = self._build_system_prompt(memory_context)
        messages = [{"role": "system", "content": system_prompt}]

        # Add short-term history (last 3 turns = 6 messages)
        for msg in self._history[-self._MAX_HISTORY:]:
            messages.append(msg)

        messages.append({"role": "user", "content": user_input})

        # 3. Call LLM — short max_tokens for spoken responses
        response = self.llm.chat(messages, max_tokens=120, temperature=0.7)
        if not response:
            return "My thinking engines seem to be offline right now."

        # 4. Clean up response
        response = self._clean_response(response)

        # 5. Update short-term history
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": response})
        if len(self._history) > self._MAX_HISTORY * 2:
            self._history = self._history[-self._MAX_HISTORY:]

        # 6. Store in long-term memory (async, non-blocking)
        if self._memory_ready and self._memory:
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

        # Compact prompt — fewer tokens = faster inference on local models
        prompt = f"""You are JARVIS, an AI assistant for {owner}. Speak concisely — responses are read aloud via TTS.

Rules:
- Keep responses to 1-3 sentences maximum.
- Be precise, direct, and slightly British in tone.
- If you don't know something, say so honestly.
- Never invent facts. Never roleplay as fictional characters.
- Use {owner}'s name sparingly."""

        if memory_context:
            prompt += f"\n\n{memory_context}"

        return prompt

    # ─── Response cleanup ────────────────────────────────────────────────

    def _clean_response(self, text):
        """Strip residual JSON, thinking tags, and artifacts."""
        if not text:
            return "I'm not sure how to respond to that."
        # Strip <think>...</think>
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Strip any JSON blocks that slipped through
        text = re.sub(r'\{[^}]*"action"[^}]*\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\{[^}]*"tool_call"[^}]*\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\{[^}]*"plan"[^}]*\}', '', text, flags=re.DOTALL)
        text = re.sub(r'```json\s*\{.*?\}\s*```', '', text, flags=re.DOTALL)
        # Strip /no_think and similar tags
        text = re.sub(r'</?no_think>', '', text)
        text = text.strip()
        return text or "Done."

    # ─── Memory storage ──────────────────────────────────────────────────

    def _store_memory(self, user_text, assistant_text):
        try:
            self._memory.store(user_text, assistant_text)
        except Exception as e:
            print(f"  [Memory store error: {e}]", flush=True)
