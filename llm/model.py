"""
J.A.R.V.I.S. LLM Layer
Multi-backend router: Groq → Gemini → Ollama (local) → Claude

Each backend speaks the same interface:
    chat(messages) → str | None
"""

import config


class LLMRouter:
    """Routes LLM requests to the best available backend."""

    def __init__(self):
        self._backends = []
        self._build_backends()

    def _build_backends(self):
        priority = config.get("brain_priority") or ["groq", "gemini", "ollama"]
        for name in priority:
            if name == "groq":
                self._backends.append(("groq", GroqBackend()))
            elif name == "gemini":
                self._backends.append(("gemini", GeminiBackend()))
            elif name == "ollama":
                self._backends.append(("ollama", OllamaBackend()))
            elif name == "claude":
                self._backends.append(("claude", ClaudeBackend()))

    def chat(self, messages, max_tokens=250, temperature=0.7):
        """Try each backend in priority order. Return first successful reply."""
        for name, backend in self._backends:
            try:
                reply = backend.chat(messages, max_tokens, temperature)
                if reply:
                    print(f"  [LLM: {name}]", flush=True)
                    return reply
            except Exception as e:
                print(f"  [LLM {name} error: {e}]", flush=True)
        return None

    def active_backend(self):
        """Return name of the first available backend."""
        for name, backend in self._backends:
            if backend.is_available():
                model = backend.model_name()
                return f"{name}/{model}" if model else name
        return "none"


# ─── Backends ────────────────────────────────────────────────────────────────

class GroqBackend:
    def is_available(self):
        return bool(config.get("groq_api_key"))

    def model_name(self):
        return config.get("groq_model") or "llama-3.3-70b-versatile"

    def chat(self, messages, max_tokens=250, temperature=0.7):
        key = config.get("groq_api_key")
        if not key:
            return None
        from groq import Groq
        client = Groq(api_key=key)
        resp = client.chat.completions.create(
            model=self.model_name(),
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content


class GeminiBackend:
    def is_available(self):
        return bool(config.get("gemini_api_key"))

    def model_name(self):
        return config.get("gemini_model") or "gemini-1.5-flash"

    def chat(self, messages, max_tokens=250, temperature=0.7):
        key = config.get("gemini_api_key")
        if not key:
            return None
        import requests
        model = self.model_name()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

        # Convert messages to Gemini format
        system_text = ""
        contents = []
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            else:
                role = "user" if m["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})

        body = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}

        r = requests.post(url, json=body, timeout=15)
        if r.status_code != 200:
            print(f"  [Gemini HTTP {r.status_code}]", flush=True)
            return None
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


class OllamaBackend:
    def is_available(self):
        try:
            import requests
            url = (config.get("ollama_url") or "http://localhost:11434") + "/api/tags"
            r = requests.get(url, timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def model_name(self):
        return config.get("ollama_model") or "mistral"

    def chat(self, messages, max_tokens=250, temperature=0.7):
        import requests
        url = (config.get("ollama_url") or "http://localhost:11434") + "/api/chat"
        r = requests.post(url, json={
            "model": self.model_name(),
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }, timeout=60)
        if r.status_code != 200:
            return None
        return r.json()["message"]["content"].strip()


class ClaudeBackend:
    def is_available(self):
        return bool(config.get("claude_api_key"))

    def model_name(self):
        return config.get("claude_model") or "claude-sonnet-4-5"

    def chat(self, messages, max_tokens=250, temperature=0.7):
        key = config.get("claude_api_key")
        if not key:
            return None
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            system = ""
            chat_msgs = []
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    chat_msgs.append(m)
            resp = client.messages.create(
                model=self.model_name(),
                max_tokens=max_tokens,
                system=system,
                messages=chat_msgs,
            )
            return resp.content[0].text
        except Exception as e:
            print(f"  [Claude error: {e}]", flush=True)
            return None
