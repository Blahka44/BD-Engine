"""
BD Auto-Engine — @justinbizdev
Scans CoinGecko every hour, finds momentum/thin-book tokens,
generates personalised DMs via Groq, sends to your Telegram.
Zero cost. Fully automated.
"""

import os
import requests
import json
import time

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

COINGECKO_URL = "https://api.coingecko.com/api/v3"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ─── STEP 1: Pull movers from CoinGecko ───────────────────────────────────────

def get_prospects():
    """
    Fetch coins with:
    - High 24h price gain (>15%) — momentum signal
    - Small-mid market cap (<$300M) — thin book likely
    - Listed on CEXs
    """
    try:
        res = requests.get(
            f"{COINGECKO_URL}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "percent_change_24h_desc",
                "per_page": 250,
                "page": 1,
                "price_change_percentage": "24h,7d",
                "sparkline": False
            },
            timeout=15
        )
        coins = res.json()

        prospects = []
        for coin in coins:
            change_24h = coin.get("price_change_percentage_24h") or 0
            market_cap = coin.get("market_cap") or 0
            volume = coin.get("total_volume") or 0

            # Signals for thin order book:
            # 1. Big move (>15% gain) = price moved easily
            # 2. Small-mid cap (<$300M) = less liquidity
            # 3. Volume/MCap ratio low = thin real buying
            vol_to_mcap = (volume / market_cap) if market_cap > 0 else 0

            if (
                change_24h > 15 and
                1_000_000 < market_cap < 300_000_000
            ):
                prospects.append({
                    "id": coin["id"],
                    "name": coin["name"],
                    "symbol": coin["symbol"].upper(),
                    "price_usd": coin["current_price"],
                    "change_24h": round(change_24h, 1),
                    "market_cap_m": round(market_cap / 1_000_000, 1),
                    "volume_m": round(volume / 1_000_000, 1),
                    "vol_to_mcap": round(vol_to_mcap, 3),
                    "image": coin.get("image", ""),
                })

        # Return top 5 highest movers
        return sorted(prospects, key=lambda x: x["change_24h"], reverse=True)[:5]

    except Exception as e:
        print(f"CoinGecko error: {e}")
        return []


# ─── STEP 2: Generate DM via Gemini ───────────────────────────────────────────

def generate_dm(prospect):
    """Use Gemini free tier to write a personalised cold DM."""

    prompt = f"""You are a crypto BD advisor writing a cold outreach DM for @justinbizdev — 
an independent advisor specialising in market structure transparency and CEX listing strategy.

Project: {prospect['name']} (${prospect['symbol']})
24h Move: +{prospect['change_24h']}%
Market Cap: ${prospect['market_cap_m']}M
Volume: ${prospect['volume_m']}M

Write TWO cold DMs:

1. TELEGRAM (max 3 lines):
- Open with their token's momentum as a compliment/observation
- Hint their market structure may not be keeping pace with the price action
- Use "market structure" NOT "market maker"  
- Never imply replacing their MM or selling a new MM
- End with a soft open question
- Sound like a knowledgeable insider, not a vendor

2. X DM (max 2 lines):
- Same rules, even shorter

Return ONLY this JSON, no markdown, no backticks:
{{
  "pain_angle": "one sentence — what's the core pain this project likely has right now",
  "who_to_contact": "founder title to search for on X/Telegram",
  "telegram_dm": "the telegram DM text",
  "x_dm": "the X DM text",
  "search_hint": "what to search on X or Telegram to find their founder e.g. @projectname founder"
}}"""

    try:
        res = requests.post(
            GEMINI_URL,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20
        )
        raw = res.json()
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"Gemini error for {prospect['name']}: {e}")
        return None


# ─── STEP 3: Send to your Telegram ────────────────────────────────────────────

def send_telegram(message):
    """Send alert to your personal Telegram via bot."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except Exception as e:
        print(f"Telegram send error: {e}")


# ─── STEP 4: Format alert message ─────────────────────────────────────────────

def format_alert(prospect, dm_data):
    urgency = "🔴 HIGH" if prospect["change_24h"] > 30 else "🟡 MEDIUM"

    return f"""⚡ <b>BD PROSPECT ALERT</b>
{urgency} URGENCY

<b>${prospect['symbol']} — {prospect['name']}</b>
📈 +{prospect['change_24h']}% in 24h
💰 Market Cap: ${prospect['market_cap_m']}M
📊 Volume: ${prospect['volume_m']}M

🎯 <b>Pain Angle:</b>
{dm_data['pain_angle']}

👤 <b>Who to Contact:</b> {dm_data['who_to_contact']}
🔍 <b>Search:</b> {dm_data['search_hint']}

─────────────────────
📱 <b>TELEGRAM DM (copy this):</b>
{dm_data['telegram_dm']}

─────────────────────
🐦 <b>X DM (copy this):</b>
{dm_data['x_dm']}

─────────────────────
👆 Copy → Find founder → Paste → Send
<i>@justinbizdev BD Engine</i>"""


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("🔍 Scanning CoinGecko for prospects...")
    prospects = get_prospects()

    if not prospects:
        print("No qualifying prospects found this scan.")
        send_telegram("🔍 BD Engine scanned — no qualifying prospects this hour. Window still open.")
        return

    print(f"✅ Found {len(prospects)} prospects. Generating DMs...")

    sent_count = 0
    for prospect in prospects:
        print(f"  → Processing {prospect['name']} (+{prospect['change_24h']}%)")
        dm_data = generate_dm(prospect)

        if dm_data:
            message = format_alert(prospect, dm_data)
            send_telegram(message)
            sent_count += 1
            time.sleep(2)  # Avoid rate limits

    print(f"✅ Done. Sent {sent_count} prospect alerts to Telegram.")


if __name__ == "__main__":
    main()
