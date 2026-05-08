import os
import requests
import json
import time

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

COINGECKO_URL = "https://api.coingecko.com/api/v3"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def get_prospects():
    try:
        res = requests.get(
            f"{COINGECKO_URL}/coins/markets",
            params={"vs_currency":"usd","order":"percent_change_24h_desc","per_page":250,"page":1,"price_change_percentage":"24h,7d","sparkline":False},
            timeout=15
        )
        coins = res.json()
        prospects = []
        for coin in coins:
            change_24h = coin.get("price_change_percentage_24h") or 0
            market_cap = coin.get("market_cap") or 0
            volume = coin.get("total_volume") or 0
            if change_24h > 15 and 1_000_000 < market_cap < 300_000_000:
                prospects.append({"name":coin["name"],"symbol":coin["symbol"].upper(),"change_24h":round(change_24h,1),"market_cap_m":round(market_cap/1_000_000,1),"volume_m":round(volume/1_000_000,1)})
        return sorted(prospects, key=lambda x: x["change_24h"], reverse=True)[:5]
    except Exception as e:
        print(f"CoinGecko error: {e}")
        return []

def generate_dm(prospect):
    prompt = f"""You are a crypto BD advisor writing cold outreach DMs for @justinbizdev.
Project: {prospect['name']} (${prospect['symbol']})
24h Move: +{prospect['change_24h']}%
Market Cap: ${prospect['market_cap_m']}M

Write TWO DMs. Rules: use "market structure" not "market maker", never imply replacing their MM, end with soft question, sound like insider not vendor, no emojis.
1. TELEGRAM: max 3 lines
2. X DM: max 2 lines

Return ONLY this JSON, no markdown:
{{"pain_angle":"one sentence pain","who_to_contact":"founder title","telegram_dm":"telegram text","x_dm":"x text","search_hint":"how to find them"}}"""
    try:
        res = requests.post(
            GROQ_URL,
            headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"},
            json={"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":prompt}],"temperature":0.7,"max_tokens":500},
            timeout=20
        )
        raw = res.json()["choices"][0]["message"]["content"]
        clean = raw.replace("```json","").replace("```","").strip()
        return json.loads(clean)
    except Exception as e:
        print(f"Groq error for {prospect['name']}: {e}")
        return None

def send_telegram(message):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":message,"parse_mode":"HTML","disable_web_page_preview":True},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

def format_alert(prospect, dm_data):
    urgency = "🔴 HIGH" if prospect["change_24h"] > 30 else "🟡 MEDIUM"
    return f"""⚡ <b>BD PROSPECT ALERT</b>
{urgency} URGENCY

<b>${prospect['symbol']} — {prospect['name']}</b>
📈 +{prospect['change_24h']}% in 24h
💰 Market Cap: ${prospect['market_cap_m']}M

🎯 <b>Pain Angle:</b> {dm_data['pain_angle']}
👤 <b>Contact:</b> {dm_data['who_to_contact']}
🔍 <b>Find them:</b> {dm_data['search_hint']}

━━━━━━━━━━━━━━━━
📱 <b>TELEGRAM DM:</b>
{dm_data['telegram_dm']}

━━━━━━━━━━━━━━━━
🐦 <b>X DM:</b>
{dm_data['x_dm']}

━━━━━━━━━━━━━━━━
<i>Copy → Find founder → Paste → Send | @justinbizdev</i>"""

def main():
    print("Scanning CoinGecko for prospects...")
    prospects = get_prospects()
    if not prospects:
        print("No qualifying prospects this scan.")
        send_telegram("🔍 BD Engine scanned — no qualifying prospects this hour.")
        return
    print(f"Found {len(prospects)} prospects. Generating DMs...")
    for prospect in prospects:
        print(f"  → {prospect['name']} (+{prospect['change_24h']}%)")
        dm_data = generate_dm(prospect)
        if dm_data:
            send_telegram(format_alert(prospect, dm_data))
            time.sleep(2)
    print("Done. All alerts sent.")

if __name__ == "__main__":
    main()
