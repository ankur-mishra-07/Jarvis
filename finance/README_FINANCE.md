# J.A.R.V.I.S. Finance Mode

Indian stock analysis, portfolio tracking, and financial planning — by voice.

## Voice commands

| Say | Does |
|-----|------|
| "stock price of Reliance" | Live NSE quote |
| "analyse Tata Motors" | Technical snapshot: SMA 50/200, RSI, 52-week position, trend verdict |
| "market summary" / "how is the market" | NIFTY, SENSEX, Bank NIFTY |
| "top gainers today" | Best/worst large caps |
| "add 10 shares of Infosys at 1500 to my portfolio" | Track a holding |
| "remove Infosys from my portfolio" | Untrack |
| "show my portfolio" | List holdings |
| "portfolio value" | Live valuation + P&L + best/worst performer |
| "finance briefing" | Market + portfolio in one shot |
| "SIP of 10000 per month for 15 years" | Projected corpus at 12% CAGR |

Data: Yahoo Finance (free, no key). Portfolio: `data/portfolio.json` (local only,
never leaves your machine).

## Getting your real asset details — what access is actually needed

**A mobile number alone cannot fetch your holdings.** Indian regulations
(rightly) require consent-based authentication for every data pull. These are
your real options, easiest first:

### 1. CSV import (free, 2 minutes, works today)
Download your holdings CSV from Zerodha Console / Groww / Upstox and we can
import it into `data/portfolio.json`. No credentials stored, fully offline.

### 2. Broker API (live holdings + order placement)
- **Zerodha Kite Connect** — ₹500/month (or ₹2000 with historical data).
  Daily login flow generates an access token; Jarvis could then fetch live
  holdings, positions, and P&L automatically.
- **Upstox API** — free. Same OAuth-style daily token.
- **5paisa / Dhan APIs** — free tiers available.

You would give Jarvis: API key + API secret (stored in `config.json`,
which is gitignored), and complete a browser login once per day.

### 3. Account Aggregator (full asset picture: bank + MF + stocks + EPF)
The RBI's AA framework (Sahamati) — apps like Finvu/OneMoney use your mobile
number to discover accounts, but **every fetch requires an OTP consent you
approve**. Individual developers can't directly join the AA network (it
requires an FIU license), but Setu and Finarkein offer sandbox/aggregation
APIs built on it.

### 4. MF Central (mutual funds only)
CAS statement via mfcentral.com — OTP to your mobile/email, downloads a
password-protected PDF that we can parse into the portfolio.

**Recommendation:** start with CSV import (option 1) now; add Upstox API
(option 2, free) if you want live sync.

## Disclaimers

Analysis is rule-based technical screening (moving averages, RSI), not
investment advice. Jarvis is not SEBI-registered. Markets carry risk —
verify before acting.
