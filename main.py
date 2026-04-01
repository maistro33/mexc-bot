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

def has_open_position(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if p["symbol"] == sym and safe(p.get("contracts")) > 0:
                return True
        return False
    except:
        return False

# ===== 🔥 NEW: TREND FILTER =====
def trend_filter(sym, direction):
    m15 = get_candles(sym, "15m", 50)
    if len(m15) < 20:
        return True

    closes = [c[4] for c in m15]
    avg = sum(closes[-20:]) / 20

    if closes[-1] > avg:
        return direction == "long"
    else:
        return direction == "short"

# ===== 🔥 NEW: RECOVERY =====
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
                trade_state[sym] = {
                    "sl": entry * 0.98,
                    "tp1": False,
                    "trail_active": False,
                    "trail_price": 0
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
    avg = sum(vols[:-1]) / len(vols[:-1])
    return vols[-1] > avg * 1.5

def orderbook_imbalance(sym):
    try:
        ob = exchange.fetch_order_book(sym, limit=10)
        bids = sum(b[1] for b in ob["bids"])
        asks = sum(a[1] for a in ob["asks"])
        return (bids - asks) / (bids + asks) if bids + asks else 0
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
    avg = sum(vols[:-1]) / len(vols[:-1])
    return vols[-1] > avg * 2

def liquidity_sweep(sym, direction):
    m5 = get_candles(sym, "5m", 30)
    if len(m5) < 10: return False
    highs = [c[2] for c in m5]
    lows = [c[3] for c in m5]
    closes = [c[4] for c in m5]

    if direction=="long":
        return lows[-1] < min(lows[:-5]) and closes[-1] > lows[-1]
    else:
        return highs[-1] > max(highs[:-5]) and closes[-1] < highs[-1]

def smart_entry(sym, direction):
    m5 = get_candles(sym, "5m", 30)
    if len(m5) < 10: return False
    highs = [c[2] for c in m5]
    lows = [c[3] for c in m5]
    closes = [c[4] for c in m5]

    if direction=="long":
        level = max(highs[:-5])
        return closes[-3] > level and lows[-1] <= level
    else:
        level = min(lows[:-5])
        return closes[-3] < level and highs[-1] >= level

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

# ===== MARKET =====
def get_symbols(volume):
    try:
        t = exchange.fetch_tickers()
        f = [(s, safe(d.get("quoteVolume"))) for s,d in t.items() if ":USDT" in s]
        f = [x for x in f if x[1]>=volume]
        f.sort(key=lambda x:x[1], reverse=True)
        return [x[0] for x in f[:TOP_COINS]]
    except:
        return []

def get_direction(sym):
    d = get_candles(sym, "1d", 50)
    if len(d)<5: return None
    highs=[c[2] for c in d]
    lows=[c[3] for c in d]
    if highs[-1]>highs[-5]: return "long"
    if lows[-1]<lows[-5]: return "short"
    return None

# ===== ENTRY ENGINE =====
def trade_engine(mode):
    while True:
        try:
            volume = SAFE_VOLUME if mode=="SAFE" else AGGR_VOLUME
            lev = SAFE_LEV if mode=="SAFE" else AGGR_LEV

            symbols = get_symbols(volume)

            for sym in symbols:

                if sym in active_trades:
                    continue

                if has_open_position(sym):
                    continue

                direction = get_direction(sym)
                if not direction:
                    continue

                # 🔥 TREND FILTER (sadece AGGRESSIVE)
                if mode=="AGGRESSIVE":
                    if not trend_filter(sym, direction):
                        continue

                score = calculate_score(sym, direction)

                if mode=="SAFE":
                    if not smart_entry(sym, direction): continue
                    if score < 4: continue

                if mode=="AGGRESSIVE":
                    if not smart_entry(sym, direction):
                        if not liquidity_sweep(sym, direction):
                            continue
                    if score < 3: continue

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = (MARGIN * lev) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                try:
                    exchange.set_leverage(lev, sym)
                except:
                    pass

                exchange.create_market_order(sym, "buy" if direction=="long" else "sell", qty)

                active_trades.add(sym)

                trade_state[sym] = {
                    "sl": price * 0.98 if direction=="long" else price * 1.02,
                    "tp1": False,
                    "trail_active": False,
                    "trail_price": 0
                }

                bot.send_message(CHAT_ID, f"🚀 {mode} {sym} {direction.upper()} SCORE:{score}")
                break

            time.sleep(12)

        except Exception as e:
            print(mode, "ERROR:", e)
            time.sleep(12)

# ===== MANAGER =====
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
                side = p["side"]
                direction = "long" if side=="long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])

                st = trade_state[sym]
                sl = st["sl"]
                risk = abs(entry - sl)
                tp1 = entry + risk if direction=="long" else entry - risk

                if (direction=="long" and price <= sl) or (direction=="short" and price >= sl):
                    exchange.create_market_order(sym, "sell" if direction=="long" else "buy", qty, params={"reduceOnly": True})
                    trade_state.pop(sym, None)
                    active_trades.discard(sym)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                if not st["tp1"] and ((direction=="long" and price >= tp1) or (direction=="short" and price <= tp1)):
                    exchange.create_market_order(sym, "sell" if direction=="long" else "buy", qty * TP_SPLIT[0], params={"reduceOnly": True})
                    st["tp1"] = True
                    st["sl"] = entry
                    st["trail_active"] = True
                    st["trail_price"] = price
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                if st["trail_active"]:
                    if direction=="long":
                        if price > st["trail_price"]:
                            st["trail_price"] = price
                        if price <= st["trail_price"] * (1 - TRAIL_GAP):
                            exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})
                            trade_state.pop(sym, None)
                            active_trades.discard(sym)
                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")
                    else:
                        if price < st["trail_price"]:
                            st["trail_price"] = price
                        if price >= st["trail_price"] * (1 + TRAIL_GAP):
                            exchange.create_market_order(sym, "buy", qty, params={"reduceOnly": True})
                            trade_state.pop(sym, None)
                            active_trades.discard(sym)
                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()
time.sleep(1)

# 🔥 RECOVERY EKLENDİ
load_open_positions()

threading.Thread(target=trade_engine, args=("SAFE",), daemon=True).start()
threading.Thread(target=trade_engine, args=("AGGRESSIVE",), daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 FINAL BOT (GÜNCEL + RECOVERY + TREND) AKTİF")
bot.infinity_polling()
