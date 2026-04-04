import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
AGGR_VOLUME = 100_000
TOP_COINS = 100
MAX_TRADES = 2

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
    "timeout": 20000
})

exchange.load_markets()

active_trades = set()
trade_state = {}
last_trade_time = {}

lock = threading.Lock()

current_margin = 5

# ===== AI CORE =====
ai_weights = {
    "trend": 1.2,
    "momentum": 1.5,
    "volume": 2.0,
    "volatility": 1.0,
    "fakeout": 1.5
}

ai_memory = {}

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0.0

def safe_api(call):
    try:
        return call()
    except Exception as e:
        print("API ERROR:", str(e))
        return None

# ===== AI DECISION =====
def decide(sym):
    try:
        m5 = safe_api(lambda: exchange.fetch_ohlcv(sym, "5m", 50))
        if not m5 or len(m5) < 20:
            return None, 0, {}, None

        closes = [x[4] for x in m5 if len(x) > 5]
        volumes = [x[5] for x in m5 if len(x) > 5]

        if len(closes) < 10 or len(volumes) < 10:
            return None, 0, {}, None

        trend = 1 if closes[-1] > sum(closes[-10:]) / 10 else 0
        momentum = 1 if closes[-1] > closes[-3] else 0

        avg_vol = sum(volumes[-10:]) / 10
        volume_spike = 1 if volumes[-1] > avg_vol * 1.3 else 0

        volatility = abs(closes[-1] - closes[-5]) / closes[-5]

        highs = [x[2] for x in m5[-10:] if len(x) > 5]
        lows = [x[3] for x in m5[-10:] if len(x) > 5]

        if len(highs) < 5 or len(lows) < 5:
            return None, 0, {}, None

        high = max(highs)
        low = min(lows)

        fakeout = 1
        if closes[-1] > high and closes[-2] < high:
            fakeout = -1
        elif closes[-1] < low and closes[-2] > low:
            fakeout = -1

        features = {
            "trend": trend,
            "momentum": momentum,
            "volume": volume_spike,
            "volatility": volatility,
            "fakeout": fakeout
        }

        score = sum(features[k] * ai_weights[k] for k in features)

        if volume_spike:
            score += 1

        direction = "long" if trend else "short"
        key = f"{sym}_{direction}"

        mem = ai_memory.get(key, {"win":1, "loss":1})
        winrate = mem["win"] / (mem["win"] + mem["loss"])

        confidence = score * winrate

        if confidence < 0.6:
            return None, confidence, features, key

        return direction, confidence, features, key

    except Exception as e:
        print("DECIDE ERROR:", e)
        return None, 0, {}, None

# ===== EXIT =====
def exit_check(sym, pnl, direction, open_time):
    if time.time() - open_time < 120:
        return False

    if pnl < -1.5 or pnl > 2:
        return True

    return False

# ===== SYMBOLS =====
def symbols():
    t = safe_api(lambda: exchange.fetch_tickers())
    if not t:
        return []

    f = [(s, safe(d.get("quoteVolume"))) for s, d in t.items() if ":USDT" in s]
    f = [x for x in f if x[1] >= AGGR_VOLUME]
    f.sort(key=lambda x: x[1], reverse=True)

    return [x[0] for x in f[:TOP_COINS]]

# ===== ENGINE =====
def engine():
    while True:
        try:
            for sym in symbols():

                if len(active_trades) >= MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                if time.time() - last_trade_time.get(sym, 0) < 8:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker.get("last"))
                if price <= 0:
                    continue

                direction, score, features, key = decide(sym)

                if not direction:
                    continue

                with lock:
                    lev = 10

                    try:
                        exchange.set_leverage(lev, sym)
                    except:
                        pass

                    market = exchange.market(sym)
                    min_q = market['limits']['amount']['min'] or 0.001

                    qty = max((current_margin * lev) / price, min_q)
                    qty = float(exchange.amount_to_precision(sym, qty))

                    # 🔥 SYMBOL FIX
                    clean_sym = sym.replace(":USDT", "")

                    print("ORDER:", clean_sym, direction, qty)

                    order = safe_api(lambda: exchange.create_market_order(
                        clean_sym,
                        "buy" if direction == "long" else "sell",
                        qty
                    ))

                    if not order:
                        continue

                    trade_state[sym] = {
                        "dir": direction,
                        "time": time.time(),
                        "features": features,
                        "key": key
                    }

                    active_trades.add(sym)
                    last_trade_time[sym] = time.time()

                    bot.send_message(CHAT_ID, f"🚀 {clean_sym} {direction} AI:{round(score,2)}")
                    break

            time.sleep(6)

        except Exception as e:
            print("ENGINE ERROR:", e)
            time.sleep(5)

# ===== MANAGE =====
def manage():
    while True:
        try:
            positions = safe_api(lambda: exchange.fetch_positions())
            if not positions:
                time.sleep(6)
                continue

            for p in positions:

                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p.get("symbol")
                if sym not in trade_state:
                    continue

                clean_sym = sym.replace(":USDT", "")

                direction = "long" if p.get("side") == "long" else "short"
                pnl = safe(p.get("unrealizedPnl"))

                st = trade_state[sym]

                if exit_check(sym, pnl, direction, st["time"]):

                    safe_api(lambda: exchange.create_market_order(
                        clean_sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    ))

                    active_trades.discard(sym)
                    trade_state.pop(sym, None)

                    # AI learning
                    k = st.get("key")
                    if k:
                        if k not in ai_memory:
                            ai_memory[k] = {"win":1, "loss":1}

                        if pnl > 0:
                            ai_memory[k]["win"] += 1
                        else:
                            ai_memory[k]["loss"] += 1

                    bot.send_message(CHAT_ID, f"❌ {clean_sym} {round(pnl,2)}")

            time.sleep(6)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FULL AI BOT AKTİF (FIXED FINAL)")
bot.infinity_polling()
