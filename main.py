import os
import time
import ccxt
import telebot
import threading
from openai import OpenAI

# ===== AI =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== SETTINGS =====
SAFE_VOLUME = 1_500_000
AGGR_VOLUME = 200_000

SAFE_LEV = 7
AGGR_LEV = 7

MARGIN = 5
TOP_COINS = 100

TP1_USDT = 0.80
STEP_LEVELS = [1, 2, 3, 4, 5]

ANTI_DUMP_PCT = 0.02
MAX_TRADES = 3

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== GLOBAL =====
active_trades = set()
trade_state = {}
memory = []
trade_lock = threading.Lock()

# ===== HELPERS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def get_candles(sym, tf, limit=100):
    try:
        return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except:
        return []

# ===== AI DECISION =====
def ai_decision(sym, direction, score, ob):
    try:
        h1 = get_candles(sym, "1h", 50)
        m5 = get_candles(sym, "5m", 30)

        if len(h1) < 30 or len(m5) < 20:
            return "SKIP"

        closes1 = [c[4] for c in h1]
        closes5 = [c[4] for c in m5]

        trend = "UP" if closes1[-1] > sum(closes1[-20:]) / 20 else "DOWN"
        momentum = "UP" if closes5[-1] > closes5[-3] else "DOWN"

        volatility = abs(closes5[-1] - closes5[-2]) / closes5[-2]

        highs = [c[2] for c in m5]
        lows = [c[3] for c in m5]

        range_size = max(highs[-10:]) - min(lows[-10:])
        range_pct = range_size / closes5[-1]

        # 🔥 FILTERLER
        if volatility < 0.002:
            return "SKIP"

        if range_pct < 0.01:
            return "SKIP"

        # 🧠 MEMORY
        wins = sum(1 for m in memory if m["result"] == "win")
        losses = sum(1 for m in memory if m["result"] == "loss")
        winrate = wins / (wins + losses) if (wins + losses) > 0 else 0.5

        prompt = f"""
You are a professional crypto trader.

Winrate: {winrate}

Trend: {trend}
Momentum: {momentum}
Volatility: {volatility}
Range: {range_pct}
Score: {score}
Orderbook: {ob}

Answer ONLY: LONG, SHORT or SKIP
"""

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )

        decision = res.choices[0].message.content.strip().upper()

        if decision == "LONG" and trend != "UP":
            return "SKIP"

        if decision == "SHORT" and trend != "DOWN":
            return "SKIP"

        if decision not in ["LONG", "SHORT"]:
            return "SKIP"

        return decision

    except Exception as e:
        print("AI ERROR:", e)
        return "SKIP"

# ===== MARKET =====
def get_symbols(volume):
    try:
        t = exchange.fetch_tickers()
        f = [(s, safe(d.get("quoteVolume"))) for s, d in t.items() if ":USDT" in s]
        f = [x for x in f if x[1] >= volume]
        f.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in f[:TOP_COINS]]
    except:
        return []

def get_direction(sym):
    d = get_candles(sym, "1d", 50)
    if len(d) < 5:
        return None
    highs = [c[2] for c in d]
    lows = [c[3] for c in d]
    if highs[-1] > highs[-5]:
        return "long"
    if lows[-1] < lows[-5]:
        return "short"
    return None

# ===== SIGNAL =====
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
        return (bids - asks) / (bids + asks) if bids + asks else 0
    except:
        return 0

def calculate_score(sym, direction):
    score = 0
    if volume_spike(sym):
        score += 2
    ob = orderbook_imbalance(sym)
    if direction == "long" and ob > 0.1:
        score += 2
    if direction == "short" and ob < -0.1:
        score += 2
    return score

# ===== ANTI DUMP (FIXED) =====
def anti_dump(sym, pnl):
    try:
        st = trade_state.get(sym)
        if not st:
            return False

        # 🔥 60 saniye koruma
        if time.time() - st["open_time"] < 60:
            return False

        # küçük zararları ignore et
        if pnl > -0.5:
            return False

        c = get_candles(sym, "3m", 3)
        if len(c) < 2:
            return False

        change = abs(c[-1][4] - c[-2][4]) / c[-2][4]

        return change > ANTI_DUMP_PCT

    except:
        return False

# ===== ENTRY =====
def trade_engine(mode):
    while True:
        try:
            vol = SAFE_VOLUME if mode == "SAFE" else AGGR_VOLUME

            for sym in get_symbols(vol):

                if sym in active_trades:
                    continue

                direction = get_direction(sym)
                if not direction:
                    continue

                score = calculate_score(sym, direction)
                if score < (4 if mode == "SAFE" else 3):
                    continue

                ob = orderbook_imbalance(sym)

                decision = ai_decision(sym, direction, score, ob)
                if decision == "SKIP":
                    continue

                direction = "long" if decision == "LONG" else "short"

                with trade_lock:
                    if len(active_trades) >= MAX_TRADES:
                        break

                    price = safe(exchange.fetch_ticker(sym)["last"])
                    qty = float(exchange.amount_to_precision(sym, (MARGIN * 7) / price))

                    exchange.create_market_order(sym, "buy" if direction == "long" else "sell", qty)

                    sl = price * 0.98 if direction == "long" else price * 1.02

                    trade_state[sym] = {
                        "sl": sl,
                        "tp1": False,
                        "step": 0,
                        "initial_risk": abs(price - sl),
                        "open_time": time.time()   # 🔥 FIX
                    }

                    active_trades.add(sym)
                    bot.send_message(CHAT_ID, f"🤖 AI {mode} {sym} {direction}")
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

                entry = safe(p["entryPrice"])
                price = safe(exchange.fetch_ticker(sym)["last"])

                side = p.get("side", "").lower()
                direction = "long" if side in ["long", "buy"] else "short"

                pnl = safe(p.get("unrealizedPnl"))
                st = trade_state[sym]

                # 🔥 ANTI-DUMP
                if anti_dump(sym, pnl):
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", qty, params={"reduceOnly": True})
                    memory.append({"symbol": sym, "result": "loss", "pnl": pnl})
                    trade_state.pop(sym, None)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID, f"⚠️ ANTI-DUMP {sym}")
                    continue

                # TP1
                if not st["tp1"] and pnl >= TP1_USDT:
                    tp_qty = float(exchange.amount_to_precision(sym, qty * 0.4))
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", tp_qty, params={"reduceOnly": True})
                    memory.append({"symbol": sym, "result": "win", "pnl": pnl})
                    st["tp1"] = True
                    st["sl"] = entry
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym} {round(pnl,2)}")

                # STOP
                if (direction == "long" and price <= st["sl"]) or (direction == "short" and price >= st["sl"]):
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", qty, params={"reduceOnly": True})
                    memory.append({"symbol": sym, "result": "loss", "pnl": pnl})
                    trade_state.pop(sym, None)
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

threading.Thread(target=trade_engine, args=("AGGRESSIVE",), daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 REAL AI FINAL AKTİF")
bot.infinity_polling()
