"""
J.A.R.V.I.S. Finance Agent — Indian stock market analysis & financial planning.

Data source: Yahoo Finance (NSE .NS / BSE .BO tickers) — free, no API key.
Portfolio: stored locally in data/portfolio.json (manual entry — see
README_FINANCE.md for how to connect real holdings via broker APIs).

DISCLAIMER: All analysis is educational. Technical signals are not
investment advice. Consult a SEBI-registered advisor before investing.
"""
from __future__ import annotations

import os
import json
import re
import time
import datetime

PORTFOLIO_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "portfolio.json"
)

DISCLAIMER = "Remember, this is technical analysis, not investment advice."

# ─── Ticker resolution ───────────────────────────────────────────────────────
# Spoken name → NSE ticker. Covers NIFTY 50 majors + common voice variations.

TICKER_MAP = {
    # Large caps
    "reliance": "RELIANCE.NS", "reliance industries": "RELIANCE.NS",
    "tcs": "TCS.NS", "tata consultancy": "TCS.NS",
    "infosys": "INFY.NS", "infy": "INFY.NS",
    "hdfc bank": "HDFCBANK.NS", "hdfc": "HDFCBANK.NS",
    "icici bank": "ICICIBANK.NS", "icici": "ICICIBANK.NS",
    "sbi": "SBIN.NS", "state bank": "SBIN.NS", "state bank of india": "SBIN.NS",
    "airtel": "BHARTIARTL.NS", "bharti airtel": "BHARTIARTL.NS",
    "itc": "ITC.NS",
    "wipro": "WIPRO.NS",
    "hcl": "HCLTECH.NS", "hcl tech": "HCLTECH.NS", "hcl technologies": "HCLTECH.NS",
    "larsen": "LT.NS", "l&t": "LT.NS", "lnt": "LT.NS", "larsen and toubro": "LT.NS",
    "axis bank": "AXISBANK.NS", "axis": "AXISBANK.NS",
    "kotak": "KOTAKBANK.NS", "kotak bank": "KOTAKBANK.NS", "kotak mahindra": "KOTAKBANK.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "bajaj finserv": "BAJAJFINSV.NS",
    "maruti": "MARUTI.NS", "maruti suzuki": "MARUTI.NS",
    # Tata Motors demerged in 2025 → TMPV (passenger) + TMCV (commercial)
    "tata motors": "TMPV.NS",
    "tata motors passenger": "TMPV.NS",
    "tata motors commercial": "TMCV.NS",
    "tata steel": "TATASTEEL.NS",
    "tata power": "TATAPOWER.NS",
    "mahindra": "M&M.NS", "mahindra and mahindra": "M&M.NS",
    "asian paints": "ASIANPAINT.NS",
    "titan": "TITAN.NS",
    "sun pharma": "SUNPHARMA.NS",
    "dr reddy": "DRREDDY.NS", "dr reddys": "DRREDDY.NS",
    "cipla": "CIPLA.NS",
    "ultratech": "ULTRACEMCO.NS", "ultratech cement": "ULTRACEMCO.NS",
    "nestle": "NESTLEIND.NS", "nestle india": "NESTLEIND.NS",
    "hindustan unilever": "HINDUNILVR.NS", "hul": "HINDUNILVR.NS",
    "ntpc": "NTPC.NS",
    "power grid": "POWERGRID.NS",
    "ongc": "ONGC.NS",
    "coal india": "COALINDIA.NS",
    "adani enterprises": "ADANIENT.NS", "adani": "ADANIENT.NS",
    "adani ports": "ADANIPORTS.NS",
    "adani green": "ADANIGREEN.NS",
    "adani power": "ADANIPOWER.NS",
    "jsw steel": "JSWSTEEL.NS",
    "hindalco": "HINDALCO.NS",
    "vedanta": "VEDL.NS",
    "tech mahindra": "TECHM.NS",
    "indusind bank": "INDUSINDBK.NS", "indusind": "INDUSINDBK.NS",
    "zomato": "ETERNAL.NS", "eternal": "ETERNAL.NS",
    "swiggy": "SWIGGY.NS",
    "paytm": "PAYTM.NS",
    "nykaa": "NYKAA.NS",
    "irctc": "IRCTC.NS",
    "lic": "LICI.NS",
    "dmart": "DMART.NS", "avenue supermarts": "DMART.NS",
    "trent": "TRENT.NS",
    "hal": "HAL.NS", "hindustan aeronautics": "HAL.NS",
    "bel": "BEL.NS", "bharat electronics": "BEL.NS",
    "bajaj auto": "BAJAJ-AUTO.NS",
    "hero motocorp": "HEROMOTOCO.NS", "hero": "HEROMOTOCO.NS",
    "eicher": "EICHERMOT.NS", "eicher motors": "EICHERMOT.NS",
    "tvs motor": "TVSMOTOR.NS", "tvs": "TVSMOTOR.NS",
    "grasim": "GRASIM.NS",
    "shree cement": "SHREECEM.NS",
    "divis lab": "DIVISLAB.NS", "divis": "DIVISLAB.NS",
    "apollo hospitals": "APOLLOHOSP.NS", "apollo": "APOLLOHOSP.NS",
    "britannia": "BRITANNIA.NS",
    "godrej consumer": "GODREJCP.NS",
    "dabur": "DABUR.NS",
    "pidilite": "PIDILITIND.NS",
    "havells": "HAVELLS.NS",
    "siemens": "SIEMENS.NS",
    "abb": "ABB.NS",
    "dlf": "DLF.NS",
    "indigo": "INDIGO.NS", "interglobe": "INDIGO.NS",
    "jio financial": "JIOFIN.NS", "jio": "JIOFIN.NS",
}

INDICES = {
    "nifty": "^NSEI", "nifty 50": "^NSEI", "nifty fifty": "^NSEI",
    "sensex": "^BSESN", "bse": "^BSESN",
    "bank nifty": "^NSEBANK", "banknifty": "^NSEBANK", "nifty bank": "^NSEBANK",
    "nifty it": "^CNXIT",
}


def resolve_ticker(name):
    """Resolve a spoken stock name to an NSE/index ticker."""
    name = name.lower().strip(" .?!,")
    # Strip filler words from voice commands
    name = re.sub(r'\b(stock|share|price|of|the|for|me|please|today|current|company|limited|ltd)\b', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    if not name:
        return None, None

    if name in INDICES:
        return INDICES[name], name

    if name in TICKER_MAP:
        return TICKER_MAP[name], name

    # Partial match — "bajaj" matches "bajaj finance" etc.
    for key, ticker in TICKER_MAP.items():
        if name in key or key in name:
            return ticker, key

    # Assume it's a direct symbol: "tatamotors" → TATAMOTORS.NS
    symbol = name.upper().replace(" ", "")
    if re.match(r'^[A-Z&-]{2,15}$', symbol):
        return f"{symbol}.NS", name

    return None, None


# ─── Data fetchers ───────────────────────────────────────────────────────────

_quote_cache = {}  # ticker → (timestamp, data)
_CACHE_TTL = 60    # seconds


def _fetch(ticker):
    """Fetch quote data with a short cache (avoids hammering Yahoo on repeats)."""
    now = time.time()
    if ticker in _quote_cache:
        ts, data = _quote_cache[ticker]
        if now - ts < _CACHE_TTL:
            return data

    import yfinance as yf
    t = yf.Ticker(ticker)
    fi = t.fast_info
    data = {
        "price": fi.last_price,
        "prev_close": fi.previous_close,
        "year_high": fi.year_high,
        "year_low": fi.year_low,
        "currency": getattr(fi, "currency", "INR"),
        "_ticker_obj": t,
    }
    _quote_cache[ticker] = (now, data)
    return data


def _pct(new, old):
    if not old:
        return 0.0
    return (new - old) / old * 100


def _fmt_inr(x):
    """Format a number in Indian style for speech: 1263.45 → '1,263 rupees 45 paise' (simplified)."""
    return f"₹{x:,.2f}"


# ─── Voice command handlers ──────────────────────────────────────────────────

def stock_quote(command):
    """'What's the stock price of Reliance' → live quote."""
    ticker, name = resolve_ticker(command)
    if not ticker:
        return ("I couldn't identify that stock. Try the company name, "
                "like Reliance, TCS, or HDFC Bank.")
    try:
        d = _fetch(ticker)
        chg = _pct(d["price"], d["prev_close"])
        direction = "up" if chg >= 0 else "down"
        display = name.title() if name else ticker
        if ticker.startswith("^"):
            return (f"{display.title()} is at {d['price']:,.0f}, "
                    f"{direction} {abs(chg):.2f} percent today.")
        return (f"{display} is trading at {_fmt_inr(d['price'])}, "
                f"{direction} {abs(chg):.2f} percent from yesterday's close.")
    except Exception as e:
        print(f"  [Finance quote error: {e}]", flush=True)
        return f"I couldn't fetch the quote for {name or 'that stock'} right now."


def analyze_stock(command):
    """
    'Analyse Tata Motors' → technical snapshot:
    price vs 50/200-day SMA, RSI, 52-week position, simple verdict.
    """
    ticker, name = resolve_ticker(command)
    if not ticker:
        return "I couldn't identify that stock. Try saying the company name."
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 60:
            return f"Not enough trading history to analyse {name}."

        close = hist["Close"]
        price = float(close.iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        # RSI (14-day)
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])

        year_high = float(close.max())
        year_low = float(close.min())
        from_high = _pct(price, year_high)
        month_chg = _pct(price, float(close.iloc[-21])) if len(close) >= 21 else 0

        # Build verdict from signals
        signals = []
        score = 0
        if price > sma50:
            signals.append("above its 50-day average")
            score += 1
        else:
            signals.append("below its 50-day average")
            score -= 1
        if sma200:
            if price > sma200:
                score += 1
            else:
                score -= 1
        if rsi >= 70:
            signals.append(f"RSI {rsi:.0f} — overbought territory")
            score -= 1
        elif rsi <= 30:
            signals.append(f"RSI {rsi:.0f} — oversold territory")
            score += 1
        else:
            signals.append(f"RSI {rsi:.0f} — neutral")

        if score >= 2:
            verdict = "The trend looks bullish"
        elif score <= -2:
            verdict = "The trend looks bearish"
        else:
            verdict = "The trend is mixed"

        display = (name or ticker).title()
        return (
            f"{display}: {_fmt_inr(price)}, {month_chg:+.1f} percent this month, "
            f"{abs(from_high):.0f} percent below its 52-week high. "
            f"It's {signals[0]}, {signals[-1]}. "
            f"{verdict}. {DISCLAIMER}"
        )
    except Exception as e:
        print(f"  [Finance analysis error: {e}]", flush=True)
        return f"Analysis failed for {name or 'that stock'} — data source may be down."


def market_summary(command=None):
    """'How is the market today' → NIFTY, SENSEX, Bank NIFTY summary."""
    try:
        parts = []
        for label, ticker in [("NIFTY", "^NSEI"), ("SENSEX", "^BSESN"), ("Bank NIFTY", "^NSEBANK")]:
            try:
                d = _fetch(ticker)
                chg = _pct(d["price"], d["prev_close"])
                arrow = "up" if chg >= 0 else "down"
                parts.append(f"{label} {d['price']:,.0f}, {arrow} {abs(chg):.2f} percent")
            except Exception:
                continue
        if not parts:
            return "Market data is unavailable right now."

        nifty_chg = None
        try:
            d = _fetch("^NSEI")
            nifty_chg = _pct(d["price"], d["prev_close"])
        except Exception:
            pass

        mood = ""
        if nifty_chg is not None:
            if nifty_chg > 0.7:
                mood = " Markets are clearly positive today."
            elif nifty_chg < -0.7:
                mood = " Markets are under pressure today."
            else:
                mood = " A fairly flat session so far."

        return ". ".join(parts) + "." + mood
    except Exception as e:
        print(f"  [Market summary error: {e}]", flush=True)
        return "I couldn't fetch market data right now."


# Liquid NIFTY names scanned for movers (keeps the scan fast: ~15 tickers)
_MOVER_SCAN = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TMPV.NS",
    "AXISBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "BAJFINANCE.NS",
]


def top_movers(command=None):
    """'Top gainers today' → best and worst from large caps."""
    try:
        import yfinance as yf
        moves = []
        data = yf.download(_MOVER_SCAN, period="2d", progress=False, group_by="ticker")
        for tk in _MOVER_SCAN:
            try:
                closes = data[tk]["Close"].dropna()
                if len(closes) >= 2:
                    chg = _pct(float(closes.iloc[-1]), float(closes.iloc[-2]))
                    moves.append((tk.replace(".NS", ""), chg))
            except Exception:
                continue
        if not moves:
            return "Couldn't fetch market movers right now."
        moves.sort(key=lambda x: x[1], reverse=True)
        best = moves[:2]
        worst = moves[-2:]
        return (
            f"Among large caps: top gainers are "
            f"{best[0][0]} {best[0][1]:+.1f} percent and {best[1][0]} {best[1][1]:+.1f} percent. "
            f"Biggest losers: {worst[1][0]} {worst[1][1]:+.1f} percent and "
            f"{worst[0][0]} {worst[0][1]:+.1f} percent."
        )
    except Exception as e:
        print(f"  [Top movers error: {e}]", flush=True)
        return "Couldn't fetch market movers right now."


# ─── Portfolio (local, manual entry) ─────────────────────────────────────────

def _load_portfolio():
    try:
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"holdings": []}


def _save_portfolio(p):
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(p, f, indent=2)


def portfolio_add(command):
    """'Add 10 shares of Reliance at 1250 to my portfolio'"""
    m = re.search(r'(\d+)\s*(?:shares?|stocks?|quantity)?\s*(?:of\s+)?([a-z &]+?)(?:\s+at\s+(?:rupees\s+)?([\d.]+))?(?:\s+to)?\s*(?:my\s+)?(?:portfolio|holdings)?$',
                  command.lower().strip(" ."))
    if not m:
        return ("To add a holding say something like: "
                "add 10 shares of Reliance at 1250 to my portfolio.")
    qty = int(m.group(1))
    name = m.group(2).strip()
    buy_price = float(m.group(3)) if m.group(3) else None

    ticker, resolved = resolve_ticker(name)
    if not ticker or ticker.startswith("^"):
        return f"I couldn't identify the stock '{name}'."

    if buy_price is None:
        try:
            buy_price = _fetch(ticker)["price"]
        except Exception:
            return f"Couldn't fetch current price for {resolved}. Say the buy price explicitly."

    p = _load_portfolio()
    p["holdings"].append({
        "ticker": ticker,
        "name": resolved,
        "qty": qty,
        "buy_price": buy_price,
        "added": datetime.date.today().isoformat(),
    })
    _save_portfolio(p)
    return f"Added {qty} shares of {resolved.title()} at {_fmt_inr(buy_price)} to your portfolio."


def portfolio_remove(command):
    """'Remove Reliance from my portfolio'"""
    ticker, resolved = resolve_ticker(command)
    if not ticker:
        return "Which stock should I remove?"
    p = _load_portfolio()
    before = len(p["holdings"])
    p["holdings"] = [h for h in p["holdings"] if h["ticker"] != ticker]
    if len(p["holdings"]) == before:
        return f"{(resolved or 'That stock').title()} isn't in your portfolio."
    _save_portfolio(p)
    return f"Removed {resolved.title()} from your portfolio."


def portfolio_view(command=None):
    """'Show my portfolio' → list holdings."""
    p = _load_portfolio()
    if not p["holdings"]:
        return ("Your portfolio is empty. Add holdings by saying: "
                "add 10 shares of Reliance at 1250 to my portfolio.")
    lines = []
    for h in p["holdings"]:
        lines.append(f"{h['qty']} {h['name'].title()}")
    return f"You hold: {', '.join(lines)}. Say 'portfolio value' for current worth."


def portfolio_value(command=None):
    """'What's my portfolio worth' → live valuation with P&L."""
    p = _load_portfolio()
    if not p["holdings"]:
        return "Your portfolio is empty — nothing to value."
    total_cost = 0.0
    total_now = 0.0
    best, worst = None, None
    for h in p["holdings"]:
        try:
            price = _fetch(h["ticker"])["price"]
        except Exception:
            continue
        cost = h["qty"] * h["buy_price"]
        now = h["qty"] * price
        total_cost += cost
        total_now += now
        pnl_pct = _pct(now, cost)
        if best is None or pnl_pct > best[1]:
            best = (h["name"], pnl_pct)
        if worst is None or pnl_pct < worst[1]:
            worst = (h["name"], pnl_pct)

    if total_cost == 0:
        return "Couldn't value the portfolio right now — market data unavailable."

    pnl = total_now - total_cost
    pnl_pct = _pct(total_now, total_cost)
    word = "up" if pnl >= 0 else "down"
    reply = (f"Your portfolio is worth {_fmt_inr(total_now)}, "
             f"{word} {_fmt_inr(abs(pnl))} — that's {abs(pnl_pct):.1f} percent "
             f"{'profit' if pnl >= 0 else 'loss'}.")
    if best and worst and best[0] != worst[0]:
        reply += (f" Best performer: {best[0].title()} {best[1]:+.1f} percent. "
                  f"Worst: {worst[0].title()} {worst[1]:+.1f} percent.")
    return reply


# ─── Daily briefing & planning ───────────────────────────────────────────────

def daily_briefing(command=None):
    """'Finance briefing' → market + portfolio in one shot."""
    market = market_summary()
    p = _load_portfolio()
    if p["holdings"]:
        port = portfolio_value()
        return f"{market} {port}"
    return f"{market} Your portfolio is empty — add holdings to get a personalised briefing."


def sip_calculator(command):
    """'SIP of 10000 for 15 years' → projected corpus at 12% CAGR."""
    m = re.search(r'(?:₹|rs\.?|rupees)?\s*([\d,]+)\s*(?:rupees|rs)?\s*(?:per month|monthly|a month)?.*?(\d+)\s*years?', command.lower())
    if not m:
        return ("Tell me the monthly amount and duration, like: "
                "SIP of 10000 per month for 15 years.")
    monthly = float(m.group(1).replace(",", ""))
    years = int(m.group(2))
    annual_rate = 0.12  # Long-term Indian equity average assumption
    r = annual_rate / 12
    n = years * 12
    fv = monthly * (((1 + r) ** n - 1) / r) * (1 + r)
    invested = monthly * n

    def _lakh_crore(x):
        if x >= 1e7:
            return f"{x/1e7:.2f} crore"
        if x >= 1e5:
            return f"{x/1e5:.1f} lakh"
        return f"{x:,.0f} rupees"

    return (f"A SIP of {monthly:,.0f} rupees monthly for {years} years at 12 percent "
            f"average returns grows to about {_lakh_crore(fv)} — "
            f"you'd invest {_lakh_crore(invested)} and gain {_lakh_crore(fv - invested)}. "
            f"Actual returns vary with the market.")
