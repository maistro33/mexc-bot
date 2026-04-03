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
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

active_trades = set()
trade_state = {}
last_trade_time = {}
memory = {}

lock = threading.Lock()

current_margin = 5
win_streak = 0
loss_streak = 0

# ===== AI WEIGHTS =====
ai_weights = {
    "trend": 1.2,
    "momentum": 1.5,
    "volume": 2.0,
    "volatility": 1.0,
    "fakeout": 1.5
}

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0.0

def safe_api(call):
    try:
        return call()
    except Exception as e:
        print("API ERROR:", str(e))
        try:
            bot.send_message(CHAT_ID, f"API ERROR: {e}")
        except:
            pass
        return None

# ===== MEMORY =====
def update_memory(sym, direction, pnl):
    if sym not in memory:
        memory[sym] = {"long_win":0,"long_loss":0,"short_win":0,"short_loss":0}

    if pnl > 0:
        memory[sym][direction + "_win"] += 1
    else:
        memory[sym][direction + "_loss"] += 1

# ===== AI DECISION =====
def decide(sym):
    try:
        m5 = safe_api(lambda: exchange.fetch_ohlcv(sym, "5m", 50))
        if not m5 or len(m5) < 20:
            return None, 0, {}

        closes = [x[4] for x in m5 if len(x) > 5]
        volumes = [x[5] for x in m5 if len(x) > 5]

        if len(closes) < 10 or len(volumes) < 10:
            return None, 0, {}

        trend = 1 if closes[-1] > sum(closes[-10:]) / 10 else 0
        momentum = 1 if closes[-1] > closes[-3] else 0

        avg_vol = sum(volumes[-10:]) / 10
        volume_spike = 1 if volumes[-1] > avg_vol * 1.3 else 0

        volatility = abs(closes[-1] - closes[-5]) / closes[-5]

        highs = [x[2] for x in m5[-10:] if len(x) > 5]
        lows = [x[3] for x in m5[-10:] if len(x) > 5]

        if len(highs) < 5 or len(lows) < 5:
            return None, 0, {}

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

        if score < 1.2:
            return None, score, features

        direction = "long" if momentum else "short"

        return direction, score, features

    except Exception as e:
        print("DECIDE ERROR:", e)
        return None, 0, {}

# ===== EXIT =====
def exit_check(sym, pnl, direction, open_time):
    if time.time() - open_time < 180:
        return False

    try:
        m5 = safe_api(lambda: exchange.fetch_ohlcv(sym, "5m", 20))
        if not m5 or len(m5) < 15:
            return False

        closes = [x[4] for x in m5 if len(x) > 5]
        if len(closes) < 10:
            return False

        trend = closes[-1] > sum(closes[-10:]) / 10

        if direction == "long" and not trend:
            return True

        if direction == "short" and trend:
            return True

        if pnl < -2:
            return True

        if pnl > 3:
            return True

        return False

    except:
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
    global current_margin

    while True:
        try:
            for sym in symbols():

                if len(active_trades) >= MAX_TRADES:
                    break

                if sym in active_trades:
                    continue

                if time.time() - last_trade_time.get(sym, 0) < 5:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker.get("last"))
                if price <= 0:
                    continue

                direction, score, features = decide(sym)

                if not direction:
                    continue

                with lock:
                    lev = 10

                    try:
                        exchange.set_margin_mode("cross", sym)
                    except:
                        pass

                    try:
                        exchange.set_leverage(lev, sym)
                    except:
                        pass

                    market = exchange.market(sym)
                    min_q = market['limits']['amount']['min'] or 0.001

                    margin = current_margin
                    qty = max((margin * lev) / price, min_q)
                    qty = float(exchange.amount_to_precision(sym, qty))

                    params = {"marginMode": "cross"}

                    order = safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction == "long" else "sell",
                        qty,
                        params=params
                    ))

                    if not order:
                        continue

                    trade_state[sym] = {
                        "dir": direction,
                        "time": time.time(),
                        "features": features
                    }

                    active_trades.add(sym)
                    last_trade_time[sym] = time.time()

                    bot.send_message(CHAT_ID, f"🚀 {sym} {direction} score:{round(score,2)}")
                    break

            time.sleep(5)

        except Exception as e:
            print("ENGINE ERROR:", e)
            time.sleep(5)

# ===== MANAGE =====
def manage():
    global current_margin, win_streak, loss_streak

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

                sym = p.get("symbol")
                if sym not in trade_state:
                    continue

                direction = "long" if p.get("side") == "long" else "short"
                pnl = safe(p.get("unrealizedPnl"))

                st = trade_state[sym]

                if exit_check(sym, pnl, direction, st["time"]):

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    ))

                    active_trades.discard(sym)
                    trade_state.pop(sym, None)

                    update_memory(sym, direction, pnl)

                    features = st.get("features", {})
                    for k, v in features.items():
                        if pnl > 0:
                            ai_weights[k] += 0.02 * v
                        else:
                            ai_weights[k] -= 0.02 * v

                    for k in ai_weights:
                        ai_weights[k] = max(0.1, min(5, ai_weights[k]))

                    if pnl > 0:
                        win_streak += 1
                        loss_streak = 0
                        current_margin += 1
                    else:
                        loss_streak += 1
                        win_streak = 0
                        current_margin -= 1

                    current_margin = max(3, min(20, current_margin))

                    bot.send_message(CHAT_ID, f"❌ {sym} PNL: {round(pnl,2)}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FULL AI BOT AKTİF (STABLE)")
bot.infinity_polling()
