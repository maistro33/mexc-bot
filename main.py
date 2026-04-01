import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
SAFE_VOLUME = 1_500_000
AGGR_VOLUME = 800_000

SAFE_LEV = 7
AGGR_LEV = 7

MARGIN = 5
TOP_COINS = 100
BUFFER_PCT = 0.0015

TP_SPLIT = [0.4, 0.3, 0.3]
TRAIL_START = 0.003
TRAIL_GAP = 0.01

TP1_USDT = 0.80
STEP_LEVELS = [1, 2, 3, 4, 5]

# 🔥 ANTI DUMP
ANTI_DUMP_PCT = 0.004
ANTI_DUMP_CANDLE = True

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

# ===== HELPERS =====
def safe(x):
    try: return float(x)
    except: return 0.0

def get_candles(sym, tf, limit=100):
    try: return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except: return []

# ===== 🔥 ANTI DUMP FUNC =====
def anti_dump(sym):
    try:
        candles = get_candles(sym, "1m", 3)
        if len(candles) < 2:
            return False

        last = candles[-1]
        prev = candles[-2]

        change = abs(last[4] - prev[4]) / prev[4]
        big_candle = abs(last[4] - last[1]) / last[1]

        return change > ANTI_DUMP_PCT or (ANTI_DUMP_CANDLE and big_candle > ANTI_DUMP_PCT)

    except:
        return False

def has_open_position(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if p["symbol"] == sym and safe(p.get("contracts")) > 0:
                return True
        return False
    except:
        return False

# ===== TREND FILTER =====
def trend_filter(sym, direction):
    m15 = get_candles(sym, "15m", 50)
    if len(m15) < 20:
        return True

    closes = [c[4] for c in m15]
    avg = sum(closes[-20:]) / 20

    return direction == "long" if closes[-1] > avg else direction == "short"

# ===== RECOVERY =====
def load_open_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p["entryPrice"])

            if sym not in trade_state:
                sl = entry * 0.98
                trade_state[sym] = {
                    "sl": sl,
                    "tp1": False,
                    "trail_active": False,
                    "trail_price": 0,
                    "step": 0,
                    "initial_risk": abs(entry - sl)
                }

                active_trades.add(sym)
                bot.send_message(CHAT_ID, f"♻️ RECOVERED {sym}")

    except Exception as e:
        print("RECOVERY ERROR:", e)

# ===== FILTERS =====
def volume_spike(sym):
    c = get_candles(sym, "5m", 20)
    if len(c) < 10: return False
    vols = [x[5] for x in c]
    return vols[-1] > (sum(vols[:-1]) / len(vols[:-1])) * 1.5

def orderbook_imbalance(sym):
    try:
        ob = exchange.fetch_order_book(sym, limit=10)
        bids = sum(b[1] for b in ob["bids"])
        asks = sum(a[1] for a in ob["asks"])
        return (bids - asks)/(bids + asks) if bids+asks else 0
    except:
        return 0

def fake_breakout(sym, direction):
    m5 = get_candles(sym, "5m", 15)
    if len(m5) < 5: return False
    highs = [c[2] for c in m5]
    lows = [c[3] for c in m5]
    return highs[-1] < max(highs[:-3]) if direction=="long" else lows[-1] > min(lows[:-3])

# ===== SMART =====
def whale_activity(sym):
    c = get_candles(sym, "1m", 10)
    if len(c) < 5: return False
    vols = [x[5] for x in c]
    return vols[-1] > (sum(vols[:-1])/len(vols[:-1]))*2

def liquidity_sweep(sym, direction):
    m5 = get_candles(sym, "5m", 30)
    if len(m5) < 10: return False
    highs = [c[2] for c in m5]
    lows = [c[3] for c in m5]
    closes = [c[4] for c in m5]

    return (lows[-1] < min(lows[:-5]) and closes[-1] > lows[-1]) if direction=="long" \
        else (highs[-1] > max(highs[:-5]) and closes[-1] < highs[-1])

def smart_entry(sym, direction):
    m5 = get_candles(sym, "5m", 30)
    if len(m5) < 10: return False
    highs = [c[2] for c in m5]
    lows = [c[3] for c in m5]
    closes = [c[4] for c in m5]

    return (closes[-3] > max(highs[:-5]) and lows[-1] <= max(highs[:-5])) if direction=="long" \
        else (closes[-3] < min(lows[:-5]) and highs[-1] >= min(lows[:-5]))

def calculate_score(sym, direction):
    score = 0
    if volume_spike(sym): score += 2
    ob = orderbook_imbalance(sym)
    if direction=="long" and ob>0.1: score+=2
    if direction=="short" and ob<-0.1: score+=2
    if fake_breakout(sym, direction): score-=3
    if whale_activity(sym): score+=2
    if liquidity_sweep(sym, direction): score+=3
    return score

# ===== ENTRY ENGINE =====
def trade_engine(mode):
    while True:
        try:
            volume = SAFE_VOLUME if mode=="SAFE" else AGGR_VOLUME
            lev = SAFE_LEV if mode=="SAFE" else AGGR_LEV

            for sym in get_symbols(volume):

                if sym in active_trades or has_open_position(sym):
                    continue

                direction = get_direction(sym)
                if not direction:
                    continue

                if mode=="AGGRESSIVE" and not trend_filter(sym, direction):
                    continue

                score = calculate_score(sym, direction)

                if (mode=="SAFE" and (not smart_entry(sym, direction) or score < 4)) \
                or (mode=="AGGRESSIVE" and score < 3):
                    continue

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = float(exchange.amount_to_precision(sym, (MARGIN * lev) / price))

                exchange.create_market_order(sym, "buy" if direction=="long" else "sell", qty)

                sl = price * 0.98 if direction=="long" else price * 1.02

                trade_state[sym] = {
                    "sl": sl,
                    "tp1": False,
                    "trail_active": False,
                    "trail_price": 0,
                    "step": 0,
                    "initial_risk": abs(price - sl)
                }

                active_trades.add(sym)
                bot.send_message(CHAT_ID, f"🚀 {mode} {sym} {direction.upper()} SCORE:{score}")
                break

            time.sleep(12)

        except Exception as e:
            print("ENTRY ERROR:", e)
            time.sleep(12)

# ===== MANAGE =====
def manage():
    while True:
        try:
            positions = exchange.fetch_positions()

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                entry = safe(p["entryPrice"])
                direction = "long" if p["side"]=="long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])

                st = trade_state[sym]

                # 🔥 ANTI DUMP
                if anti_dump(sym):
                    exchange.create_market_order(sym, "sell" if direction=="long" else "buy", qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID, f"⚠️ ANTI-DUMP EXIT {sym}")
                    continue

                pnl = safe(p.get("unrealizedPnl"))

                # TP1
                if not st["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, "sell" if direction=="long" else "buy", qty*0.4, params={"reduceOnly": True})
                    st["tp1"] = True
                    st["sl"] = entry
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym} (+{round(pnl,2)} USDT)")

                # STEP
                if st["tp1"]:
                    risk = st["initial_risk"]
                    current_r = abs(price - entry) / risk if risk > 0 else 0

                    for lvl in STEP_LEVELS:
                        if current_r >= lvl and st["step"] < lvl:
                            st["step"] = lvl
                            st["sl"] = entry + (lvl - 1) * risk if direction=="long" else entry - (lvl - 1) * risk
                            bot.send_message(CHAT_ID, f"📈 STEP {lvl} {sym}")

                # STOP
                if (direction=="long" and price <= st["sl"]) or (direction=="short" and price >= st["sl"]):
                    exchange.create_market_order(sym, "sell" if direction=="long" else "buy", qty, params={"reduceOnly": True})
                    trade_state.pop(sym)
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

load_open_positions()

threading.Thread(target=trade_engine, args=("SAFE",), daemon=True).start()
threading.Thread(target=trade_engine, args=("AGGRESSIVE",), daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FINAL BOT (ANTI-DUMP + STEP FIX)")
bot.infinity_polling()
