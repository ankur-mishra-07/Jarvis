"""
J.A.R.V.I.S. Claude Brain
Connects to Claude API for intelligent conversational responses.
Falls back gracefully when no API key is configured.
"""

import config

SYSTEM_PROMPT = """You are J.A.R.V.I.S., a personal AI assistant inspired by the AI from Iron Man.
You are witty, intelligent, and always helpful. You speak concisely — keep responses under 2-3 sentences
since they will be spoken aloud via text-to-speech. Be direct, charming, and slightly British in tone.
The user's name is {owner}. Address them respectfully.
You handle general knowledge questions, advice, recommendations, explanations, and conversation.
If asked to perform a system action (open apps, set timers, etc.), politely say you'll handle it."""


def ask_claude(user_message, conversation_history=None):
    """
    Send a message to Claude and get a response.
    Returns (response_text, updated_history) or (None, history) on failure.
    """
    api_key = config.get("claude_api_key")
    if not api_key:
        return None, conversation_history

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        owner = config.get("owner_name")
        system = SYSTEM_PROMPT.format(owner=owner)

        # Build messages with conversation history (keep last 10 turns)
        messages = []
        if conversation_history:
            messages = conversation_history[-10:]
        messages.append({"role": "user", "content": user_message})

        response = client.messages.create(
            model=config.get("claude_model"),
            max_tokens=200,
            system=system,
            messages=messages,
        )

        reply = response.content[0].text

        # Update history
        messages.append({"role": "assistant", "content": reply})

        return reply, messages

    except ImportError:
        print("  [Claude: anthropic package not installed]", flush=True)
        return None, conversation_history
    except Exception as e:
        error_str = str(e).lower()
        # Log the error but NEVER speak it — let the router fall back to the next brain
        # or handle gracefully. Speaking "your API key is invalid" mid-conversation is jarring.
        if any(k in error_str for k in ("credit", "billing", "quota", "payment")):
            print("  [Claude: billing/credit issue — falling back]", flush=True)
        elif any(k in error_str for k in ("auth", "invalid", "permission", "forbidden", "401", "403")):
            print("  [Claude: auth error — API key may be expired. Falling back.]", flush=True)
        else:
            print(f"  [Claude error: {e}]", flush=True)
        return None, conversation_history


def is_configured():
    """Check if Claude API is set up."""
    return bool(config.get("claude_api_key"))
