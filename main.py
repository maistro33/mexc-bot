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
TOP_COINS = 100

ANTI_DUMP_PCT = 0.02
MAX_TRADES = 2

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
    "timeout": 30000
})

exchange.load_markets()

active_trades = set()
trade_state = {}
lock = threading.Lock()

# ===== MEMORY =====
trade_history = []
pattern_memory = []

MAX_HISTORY = 20
MAX_PATTERN = 50

# ===== SAFE API =====
def safe_api(call, retries=3):
    for _ in range(retries):
        try:
            return call()
        except Exception as e:
            print("API ERROR:", e)
            time.sleep(2)
    return None

# ===== HELPERS =====
def safe(x):
    try: return float(x)
    except: return 0.0

def get_candles(sym, tf, limit=100):
    return safe_api(lambda: exchange.fetch_ohlcv(sym, tf, limit=limit)) or []

def orderbook_imbalance(sym):
    try:
        ob = safe_api(lambda: exchange.fetch_order_book(sym, 5))
        if not ob:
            return 0
        bids = sum(b[1] for b in ob["bids"])
        asks = sum(a[1] for a in ob["asks"])
        return (bids - asks)/(bids + asks) if bids+asks else 0
    except:
        return 0

# ===== PATTERN SCORE =====
def pattern_score(current):
    score = 0
    count = 0

    for p in pattern_memory:
        if abs(p["volatility"] - current["volatility"]) < 0.002:
            if abs(p["range"] - current["range"]) < 0.01:
                if p["trend"] == current["trend"]:
                    if p["momentum"] == current["momentum"]:
                        count += 1
                        if p["result"] == "win":
                            score += 1
                        else:
                            score -= 1

    return score, count

# ===== LOAD POSITIONS =====
def load_positions():
    positions = safe_api(lambda: exchange.fetch_positions())
    if not positions:
        return

    for p in positions:
        qty = safe(p.get("contracts"))
        if qty <= 0:
            continue

        sym = p["symbol"]
        entry = safe(p["entryPrice"])
        side = p.get("side","").lower()

        if side in ["long","buy"]:
            sl = entry * 0.98
            direction = "long"
        else:
            sl = entry * 1.02
            direction = "short"

        trade_state[sym] = {
            "entry": entry,
            "sl": sl,
            "risk": abs(entry - sl),
            "step": 0,
            "direction": direction,
            "open_time": time.time()
        }

        active_trades.add(sym)

# ===== AI =====
def ai_decision(sym):

    try:
        h1 = get_candles(sym, "1h", 50)
        m5 = get_candles(sym, "5m", 30)

        if len(h1) < 30 or len(m5) < 20:
            return None

        closes1 = [c[4] for c in h1]
        closes5 = [c[4] for c in m5]

        trend = "UP" if closes1[-1] > sum(closes1[-20:])/20 else "DOWN"
        momentum = "UP" if closes5[-1] > closes5[-3] else "DOWN"

        volatility = abs(closes5[-1]-closes5[-2]) / closes5[-2]

        highs = [c[2] for c in m5]
        lows = [c[3] for c in m5]
        range_pct = (max(highs[-10:]) - min(lows[-10:])) / closes5[-1]

        ob = orderbook_imbalance(sym)

        pattern = {
            "trend": trend,
            "momentum": momentum,
            "volatility": round(volatility,4),
            "range": round(range_pct,4),
            "ob": round(ob,2)
        }

        score, count = pattern_score(pattern)
        history_str = ",".join(trade_history[-10:])

        prompt = f"""
You are a professional crypto trader.

Recent trades: {history_str}
PatternScore: {score}
Samples: {count}

If score negative → avoid trade
If score positive → allow trade

Trend: {trend}
Momentum: {momentum}
Volatility: {volatility}
Range: {range_pct}
Orderbook: {ob}

Answer:
ENTER_LONG
ENTER_SHORT
SKIP
"""

        res = safe_api(lambda: client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.2
        ))

        if not res:
            return None

        txt = res.choices[0].message.content.upper()

        if "ENTER_LONG" in txt:
            return "long", pattern
        elif "ENTER_SHORT" in txt:
            return "short", pattern

        return None

    except:
        return None

# ===== SYMBOLS =====
def get_symbols():
    t = safe_api(lambda: exchange.fetch_tickers())
    if not t:
        return []

    f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
    f = [x for x in f if x[1] >= AGGR_VOLUME]
    f.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in f[:TOP_COINS]]

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

                result = ai_decision(sym)
                if not result:
                    continue

                direction, pattern = result

                with lock:
                    price = safe(safe_api(lambda: exchange.fetch_ticker(sym))["last"])
                    qty = float(exchange.amount_to_precision(sym, (MARGIN * LEVERAGE) / price))

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction=="long" else "sell",
                        qty
                    ))

                    sl = price * 0.98 if direction=="long" else price * 1.02

                    trade_state[sym] = {
                        "entry": price,
                        "sl": sl,
                        "risk": abs(price - sl),
                        "step": 0,
                        "direction": direction,
                        "pattern": pattern,
                        "open_time": time.time()
                    }

                    active_trades.add(sym)
                    bot.send_message(CHAT_ID, f"🤖 AI {sym} {direction}")
                    break

            time.sleep(15)

        except Exception as e:
            print(e)
            time.sleep(10)

# ===== MANAGE =====
def manage():
    while True:
        try:
            positions = safe_api(lambda: exchange.fetch_positions())
            if not positions:
                time.sleep(7)
                continue

            for p in positions:

                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                st = trade_state[sym]
                entry = st["entry"]
                direction = st["direction"]
                pattern = st.get("pattern")

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])
                pnl = safe(p.get("unrealizedPnl"))

                if anti_dump(sym, pnl):
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        qty,
                        params={"reduceOnly":True}
                    ))

                    trade_state.pop(sym,None)
                    active_trades.discard(sym)

                    trade_history.append("loss")

                    if pattern:
                        pattern["result"] = "loss"
                        pattern_memory.append(pattern)

                    continue

                r = abs(price - entry) / st["risk"] if st["risk"] > 0 else 0

                if r >= 0.5 and st["step"] < 1:
                    st["step"] = 1
                    st["sl"] = entry

                elif r >= 1 and st["step"] < 2:
                    st["step"] = 2
                    st["sl"] = entry + st["risk"] if direction=="long" else entry - st["risk"]

                elif r >= 2 and st["step"] < 3:
                    st["step"] = 3
                    st["sl"] = entry + 2*st["risk"] if direction=="long" else entry - 2*st["risk"]

                if (direction=="long" and price <= st["sl"]) or (direction=="short" and price >= st["sl"]):
                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        qty,
                        params={"reduceOnly":True}
                    ))

                    trade_state.pop(sym,None)
                    active_trades.discard(sym)

                    result = "win" if pnl > 0 else "loss"
                    trade_history.append(result)

                    if pattern:
                        pattern["result"] = result
                        pattern_memory.append(pattern)

                    if len(pattern_memory) > MAX_PATTERN:
                        pattern_memory.pop(0)

                    bot.send_message(CHAT_ID, f"❌ CLOSE {sym}")

            time.sleep(7)

        except Exception as e:
            print(e)
            time.sleep(7)

# ===== START =====
safe_api(lambda: exchange.fetch_balance())

bot.remove_webhook()
time.sleep(1)

load_positions()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 LEVEL 2 AI ACTIVE")
bot.infinity_polling()
