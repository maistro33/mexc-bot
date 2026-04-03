import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
TOP_COINS = 120
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
last_trade_time = {}
memory = {}

lock = threading.Lock()

current_margin = 5
win_streak = 0
loss_streak = 0

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0.0

def safe_api(call):
    try:
        return call()
    except:
        return None

# ===== MEMORY =====
def update_memory(sym, direction, pnl):
    if sym not in memory:
        memory[sym] = {"long_win":0,"long_loss":0,"short_win":0,"short_loss":0}

    if pnl > 0:
        if direction == "long":
            memory[sym]["long_win"] += 1
        else:
            memory[sym]["short_win"] += 1
    else:
        if direction == "long":
            memory[sym]["long_loss"] += 1
        else:
            memory[sym]["short_loss"] += 1

def get_winrate(sym, direction):
    m = memory.get(sym)
    if not m:
        return 0.5

    if direction == "long":
        w = m["long_win"]
        l = m["long_loss"]
    else:
        w = m["short_win"]
        l = m["short_loss"]

    total = w + l
    if total < 5:
        return 0.5

    return w / total

# ===== LEVERAGE =====
def get_lev(score):
    if score >= 5: return 12
    if score >= 3: return 8
    return 5

# ===== DECISION (AGGRESSIVE + THINKING) =====
def decide(sym):
    try:
        m5 = exchange.fetch_ohlcv(sym, "5m", 30)
        closes = [x[4] for x in m5]

        trend = closes[-1] > sum(closes[-10:]) / 10
        momentum = closes[-1] > closes[-3]

        up = closes[-1] > closes[-2] > closes[-3]
        down = closes[-1] < closes[-2] < closes[-3]

        score = 0

        if trend: score += 1
        if momentum: score += 2
        if up or down: score += 2

        confidence = score / 5

        # ❌ zayıf sinyal
        if confidence < 0.4:
            return None, score

        # ⚖️ orta sinyal → 1 tur bekle
        if 0.4 <= confidence < 0.7:
            if sym not in trade_state:
                trade_state[sym] = {"wait": True}
                return None, score

            if trade_state[sym].get("wait"):
                trade_state[sym]["wait"] = False
                return None, score

        direction = "long" if momentum else "short"

        # MEMORY filtresi
        wr = get_winrate(sym, direction)
        if wr < 0.3:
            return None, score

        return direction, score

    except:
        return None, 0

# ===== EXIT =====
def exit_check(sym, pnl, direction, open_time):
    if time.time() - open_time < 60:
        return False

    if abs(pnl) < 0.2:
        return False

    try:
        m5 = exchange.fetch_ohlcv(sym, "5m", 20)
        closes = [x[4] for x in m5]

        trend = closes[-1] > sum(closes[-10:]) / 10
        momentum = closes[-1] > closes[-3]

        if direction == "long" and not trend:
            return True

        if direction == "short" and trend:
            return True

        if pnl < -1:
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

                if time.time() - last_trade_time.get(sym, 0) < 10:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker["last"])

                if price < 0.001 or price > 200:
                    continue

                direction, score = decide(sym)

                if not direction:
                    continue

                with lock:

                    lev = get_lev(score)

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

                    risk_multiplier = 1 + (win_streak * 0.2)
                    margin = current_margin * risk_multiplier

                    qty = max((margin * lev) / price, min_q)
                    qty = float(exchange.amount_to_precision(sym, qty))

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction == "long" else "sell",
                        qty
                    ))

                    trade_state[sym] = {
                        "dir": direction,
                        "time": time.time()
                    }

                    active_trades.add(sym)
                    last_trade_time[sym] = time.time()

                    bot.send_message(CHAT_ID, f"🚀 {sym} {direction} x{lev} score:{score}")
                    break

            time.sleep(8)

        except:
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

                sym = p["symbol"]

                if sym not in trade_state:
                    continue

                direction = "long" if p["side"] == "long" else "short"
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

                    if pnl > 0:
                        win_streak += 1
                        loss_streak = 0
                        current_margin += 1
                    else:
                        loss_streak += 1
                        win_streak = 0
                        current_margin -= 1

                    current_margin = max(3, min(15, current_margin))

                    bot.send_message(CHAT_ID, f"❌ {sym} {round(pnl,2)}")

            time.sleep(5)

        except:
            time.sleep(5)

# ===== START =====
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 SMART AGGRESSIVE AI AKTİF")
bot.infinity_polling()
