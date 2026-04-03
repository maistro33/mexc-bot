
import os
import time
import ccxt
import telebot
import threading
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
LEVERAGE = 7
MARGIN = 5
TOP_COINS = 20

ANTI_DUMP_PCT = 0.02
MAX_TRADES = 2

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

# ===== HELPERS =====
def safe(x):
    try: return float(x)
    except: return 0.0

def get_candles(sym, tf, limit=100):
    try: return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except: return []

# ===== LOAD OPEN POSITIONS =====
def load_positions():
    try:
        for p in exchange.fetch_positions():
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p["entryPrice"])
            sl = entry * 0.98

            trade_state[sym] = {
                "entry": entry,
                "sl": sl,
                "risk": abs(entry - sl),
                "step": 0,
                "open_time": time.time()
            }

            active_trades.add(sym)
    except:
        pass

# ===== AI =====
def ai_decision(sym, score, ob):
    try:
        h1 = get_candles(sym, "1h", 50)
        m5 = get_candles(sym, "5m", 30)

        if len(h1) < 30 or len(m5) < 20:
            return "SKIP"

        closes1 = [c[4] for c in h1]
        closes5 = [c[4] for c in m5]

        trend = "UP" if closes1[-1] > sum(closes1[-20:])/20 else "DOWN"
        volatility = abs(closes5[-1] - closes5[-2]) / closes5[-2]

        highs = [c[2] for c in m5]
        lows = [c[3] for c in m5]
        range_pct = (max(highs[-10:]) - min(lows[-10:])) / closes5[-1]

        if volatility < 0.002 or range_pct < 0.01:
            return "SKIP"

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":f"Trend:{trend} Score:{score} OB:{ob} LONG SHORT or SKIP"}],
            temperature=0.2
        )

        d = res.choices[0].message.content.strip().upper()

        if d == "LONG" and trend != "UP":
            return "SKIP"
        if d == "SHORT" and trend != "DOWN":
            return "SKIP"

        return d if d in ["LONG","SHORT"] else "SKIP"

    except:
        return "SKIP"

# ===== MARKET =====
def get_symbols():
    try:
        t = exchange.fetch_tickers()
        f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
        f = [x for x in f if x[1] >= AGGR_VOLUME]
        f.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in f[:TOP_COINS]]
    except:
        return []

def volume_spike(sym):
    c = get_candles(sym, "5m", 20)
    if len(c) < 10:
        return False
    v = [x[5] for x in c]
    return v[-1] > (sum(v[:-1]) / len(v[:-1])) * 1.5

def orderbook_imbalance(sym):
    try:
        ob = exchange.fetch_order_book(sym, 10)
        bids = sum(b[1] for b in ob["bids"])
        asks = sum(a[1] for a in ob["asks"])
        return (bids - asks)/(bids + asks) if bids+asks else 0
    except:
        return 0

def score(sym):
    s = 0
    if volume_spike(sym): s += 2
    ob = orderbook_imbalance(sym)
    if abs(ob) > 0.1: s += 2
    return s

# ===== ANTI-DUMP =====
def anti_dump(sym, pnl):
    st = trade_state.get(sym)
    if not st:
        return False

    if time.time() - st["open_time"] < 60:
        return False

    if pnl > -0.5:
        return False

    c = get_candles(sym, "3m", 3)
    if len(c) < 2:
        return False

    change = abs(c[-1][4] - c[-2][4]) / c[-2][4]
    return change > ANTI_DUMP_PCT

# ===== ENTRY =====
def engine():
    while True:
        try:
            for sym in get_symbols():

                if len(active_trades) >= MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                sc = score(sym)
                if sc < 3:
                    continue

                ob = orderbook_imbalance(sym)
                d = ai_decision(sym, sc, ob)

                if d == "SKIP":
                    continue

                direction = "long" if d == "LONG" else "short"

                with lock:
                    if len(active_trades) >= MAX_TRADES:
                        break

                    price = safe(exchange.fetch_ticker(sym)["last"])
                    qty = float(exchange.amount_to_precision(sym, (MARGIN * LEVERAGE) / price))

                    exchange.create_market_order(sym, "buy" if direction=="long" else "sell", qty)

                    sl = price * 0.98 if direction=="long" else price * 1.02

                    trade_state[sym] = {
                        "entry": price,
                        "sl": sl,
                        "risk": abs(price - sl),
                        "step": 0,
                        "open_time": time.time()
                    }

                    active_trades.add(sym)
                    bot.send_message(CHAT_ID, f"🤖 {sym} {direction}")
                    break

            time.sleep(10)

        except Exception as e:
            print("ENTRY ERROR:", e)
            time.sleep(10)

# ===== MANAGE =====
def manage():
    while True:
        try:
            for p in exchange.fetch_positions():

                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                st = trade_state[sym]
                entry = st["entry"]

                price = safe(exchange.fetch_ticker(sym)["last"])
                side = p.get("side","").lower()
                direction = "long" if side in ["long","buy"] else "short"

                pnl = safe(p.get("unrealizedPnl"))

                # ANTI-DUMP
                if anti_dump(sym, pnl):
                    exchange.create_market_order(sym, "sell" if direction=="long" else "buy", qty, params={"reduceOnly":True})
                    trade_state.pop(sym,None)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID, f"⚠️ ANTI-DUMP {sym}")
                    continue

                # R hesap
                r = abs(price - entry) / st["risk"] if st["risk"] > 0 else 0

                # STEP SYSTEM
                if r >= 0.5 and st["step"] < 1:
                    st["step"] = 1
                    st["sl"] = entry
                    bot.send_message(CHAT_ID, f"📈 STEP1 BE {sym}")

                elif r >= 1 and st["step"] < 2:
                    st["step"] = 2
                    st["sl"] = entry + st["risk"] if direction=="long" else entry - st["risk"]
                    bot.send_message(CHAT_ID, f"📈 STEP2 PROFIT {sym}")

                elif r >= 2 and st["step"] < 3:
                    st["step"] = 3
                    st["sl"] = entry + 2*st["risk"] if direction=="long" else entry - 2*st["risk"]
                    bot.send_message(CHAT_ID, f"📈 STEP3 {sym}")

                # STOP
                if (direction=="long" and price <= st["sl"]) or (direction=="short" and price >= st["sl"]):
                    exchange.create_market_order(sym, "sell" if direction=="long" else "buy", qty, params={"reduceOnly":True})
                    trade_state.pop(sym,None)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()
time.sleep(1)

load_positions()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 STEP AI BOT ACTIVE")
bot.infinity_polling()
