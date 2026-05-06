"""Web search and information retrieval tools."""

import re
from .registry import tool


@tool("web_search", "Search the internet for information",
      {"query": "The search query"})
def web_search(query, **kw):
    """Search DuckDuckGo + Wikipedia. No API key needed."""

    # Try Wikipedia first for factual queries
    wiki = _wikipedia_search(query)
    if wiki:
        return wiki

    # DuckDuckGo fallback
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results = []
        for attempt in range(2):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))
                if results:
                    break
            except Exception:
                if attempt == 1:
                    return None

        if not results:
            return "No results found."

        # Filter and score results
        best = max(results, key=lambda r: len(r.get("body", "")))
        body = best.get("body", "").strip()
        if len(body) < 30:
            return "No useful results found."

        # Clean up
        body = re.sub(r'^[A-Z][a-z]{2}\s+\d+,\s+\d{4}\s*[·•]\s*', '', body)
        sentences = re.split(r'(?<=[.!?])\s+', body)
        answer = next((s for s in sentences if len(s) >= 30), body)
        return answer[:400]

    except Exception as e:
        return f"Search error: {e}"


@tool("wikipedia", "Look up a topic on Wikipedia",
      {"topic": "The topic to look up"})
def wikipedia_lookup(topic, **kw):
    result = _wikipedia_search(topic)
    return result or f"No Wikipedia article found for '{topic}'."


def _wikipedia_search(query):
    """Hit Wikipedia REST API — free, no key needed."""
    try:
        import requests
        q = query.lower().strip(" ?.")

        # Strip question starters
        term = re.sub(
            r'^(who|what|when|where|how|tell me about|define|meaning of|'
            r'capital of|population of|history of)\s+(is|are|was|were|the|a|an)?\s*',
            '', q
        )
        term = re.sub(r'\b(current|currently|latest|now|today|recent)\b', '', term)
        term = re.sub(r'\s+', ' ', term).strip(" ?.")
        if not term or len(term) < 2:
            return None

        # Direct lookup
        title = term[0].upper() + term[1:]
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
        r = requests.get(url, timeout=6, headers={"User-Agent": "Jarvis/2.0"})
        if r.status_code == 200:
            extract = r.json().get("extract", "")
            if extract and len(extract) > 20:
                first = re.split(r'(?<=[.!?])\s', extract)[0]
                return first[:400] if len(first) >= 20 else extract[:400]

        # Opensearch fallback
        sr = requests.get("https://en.wikipedia.org/w/api.php", timeout=6,
                          params={"action": "opensearch", "search": term,
                                  "limit": 1, "format": "json"},
                          headers={"User-Agent": "Jarvis/2.0"})
        if sr.status_code == 200 and sr.json()[1]:
            top = sr.json()[1][0]
            r2 = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{top.replace(' ', '_')}",
                timeout=6, headers={"User-Agent": "Jarvis/2.0"})
            if r2.status_code == 200:
                extract = r2.json().get("extract", "")
                if extract:
                    first = re.split(r'(?<=[.!?])\s', extract)[0]
                    return first[:400]
        return None
    except Exception:
        return None
