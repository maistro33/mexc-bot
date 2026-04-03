import os
import time
import ccxt
import telebot
import threading
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
TOP_COINS = 100
MAX_TRADES = 1

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

active_trades = set()
trade_state = {}
lock = threading.Lock()

# ===== RISK =====
current_margin = 5
win_count = 0
loss_count = 0

# ===== SAFE =====
def safe_api(call):
    try:
        return call()
    except Exception as e:
        print("API ERROR:", e)
        return None

def safe(x):
    try: return float(x)
    except: return 0.0

# ===== AI CHAT =====
def ai_chat(prompt):
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.3
        )
        return res.choices[0].message.content.strip()
    except:
        return "AI hata"

# ===== ORDERBOOK =====
def orderbook_imbalance(sym):
    ob = safe_api(lambda: exchange.fetch_order_book(sym, 5))
    if not ob:
        return 0
    bids = sum(b[1] for b in ob["bids"])
    asks = sum(a[1] for a in ob["asks"])
    return (bids - asks)/(bids + asks) if bids+asks else 0

# ===== LEVERAGE =====
def get_dynamic_leverage(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [x[4] for x in c]

        trend_strength = abs(closes[-1] - closes[-5]) / closes[-5]
        ob = orderbook_imbalance(sym)

        if trend_strength > 0.01 and ob > 0:
            return 10
        elif trend_strength > 0.005:
            return 7
        else:
            return 4
    except:
        return 5

# ===== AI ENTRY =====
def ai_decision(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "5m", limit=30)
        closes = [x[4] for x in c]

        trend = closes[-1] > sum(closes[-10:])/10
        momentum = closes[-1] > closes[-3]
        ob = orderbook_imbalance(sym)

        if trend and momentum and ob > 0:
            return "long"

        if (not trend) and (not momentum) and ob < 0:
            return "short"

        return None
    except:
        return None

# ===== AI EXIT =====
def ai_exit(sym, pnl, direction):
    try:
        c = exchange.fetch_ohlcv(sym, "5m", limit=20)
        closes = [x[4] for x in c]

        trend = closes[-1] > sum(closes[-10:])/10
        momentum = closes[-1] > closes[-3]

        prompt = f"""
Türkçe.
Tek kelime:

CLOSE veya HOLD

PnL: {pnl}
Trend: {trend}
Momentum: {momentum}
Direction: {direction}
"""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0
        )

        txt = res.choices[0].message.content.upper()

        return "CLOSE" in txt

    except:
        return False

# ===== SYMBOLS =====
def get_symbols():
    t = safe_api(lambda: exchange.fetch_tickers())
    if not t:
        return []

    f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
    f = [x for x in f if x[1] >= AGGR_VOLUME]
    f.sort(key=lambda x: x[1], reverse=True)

    return [x[0] for x in f[:TOP_COINS]]

# ===== ENTRY =====
def engine():
    global current_margin

    while True:
        try:
            for sym in get_symbols():

                if len(active_trades) >= MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])

                # FILTER
                if price < 0.001 or price > 200:
                    continue

                direction = ai_decision(sym)
                if not direction:
                    continue

                with lock:

                    lev = get_dynamic_leverage(sym)

                    # SAFE LEVERAGE
                    try:
                        exchange.set_margin_mode("cross", sym)
                    except:
                        pass

                    try:
                        exchange.set_leverage(lev, sym)
                    except:
                        pass

                    market = exchange.market(sym)
                    min_qty = market['limits']['amount']['min'] or 0.001

                    qty = (current_margin * lev) / price
                    qty = max(qty, min_qty)
                    qty = float(exchange.amount_to_precision(sym, qty))

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction == "long" else "sell",
                        qty
                    ))

                    trade_state[sym] = {
                        "direction": direction,
                        "leverage": lev
                    }

                    active_trades.add(sym)

                    yorum = ai_chat(f"""
Türkçe yaz
max 2 satır

{sym} {direction}
""")

                    bot.send_message(CHAT_ID, f"🚀 {sym} {direction} x{lev}\n{yorum}")
                    break

            time.sleep(10)

        except Exception as e:
            print("ENTRY ERROR:", e)
            time.sleep(5)

# ===== MANAGE =====
def manage():
    global current_margin, win_count, loss_count

    while True:
        try:
            positions = safe_api(lambda: exchange.fetch_positions())
            if not positions:
                time.sleep(5)
                continue

            for p in positions:

                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                direction = "long" if p["side"] == "long" else "short"

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                pnl = safe(p.get("unrealizedPnl"))

                # AI EXIT
                if ai_exit(sym, pnl, direction):

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    ))

                    active_trades.discard(sym)
                    trade_state.pop(sym, None)

                    # RISK UPDATE
                    if pnl > 0:
                        win_count += 1
                        current_margin += 1
                    else:
                        loss_count += 1
                        current_margin -= 1

                    if current_margin < 3:
                        current_margin = 3
                    if current_margin > 12:
                        current_margin = 12

                    yorum = ai_chat(f"""
Türkçe yaz
max 2 satır

PnL: {pnl}
""")

                    bot.send_message(CHAT_ID, f"❌ {sym} {round(pnl,2)}\n{yorum}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 PRO AI TRADER AKTİF")
bot.infinity_polling()
