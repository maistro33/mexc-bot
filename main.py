import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
TOP_COINS = 100
MAX_TRADES = 2

TP1_USDT = 0.25
TRAIL_GAP = 0.01

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

active_trades = set()
trade_state = {}
lock = threading.Lock()

# ===== SAFE =====
def safe(x):
    try: return float(x)
    except: return 0.0

def safe_api(call):
    try:
        return call()
    except Exception as e:
        print("API ERROR:", e)
        return None

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
            side = p["side"]

            trade_state[sym] = {
                "direction": "long" if side=="long" else "short",
                "entry": entry,
                "tp1": True,
                "step": 1,
                "trail_active": True,
                "trail_price": entry,
                "closing": False
            }

            active_trades.add(sym)

            bot.send_message(CHAT_ID, f"♻️ RECOVER {sym}")

    except Exception as e:
        print("RECOVERY ERROR:", e)

# ===== ORDERBOOK =====
def orderbook(sym):
    ob = safe_api(lambda: exchange.fetch_order_book(sym, 5))
    if not ob:
        return 0
    bids = sum(b[1] for b in ob["bids"])
    asks = sum(a[1] for a in ob["asks"])
    return (bids - asks)/(bids + asks) if bids+asks else 0

# ===== AI ENTRY =====
def decide(sym):
    try:
        c = exchange.fetch_ohlcv(sym, "5m", limit=30)
        closes = [x[4] for x in c]

        trend = closes[-1] > sum(closes[-10:])/10
        momentum = closes[-1] > closes[-3]
        ob = orderbook(sym)

        if trend and momentum and ob > 0:
            return "long"

        if not trend and not momentum and ob < 0:
            return "short"

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

# ===== ENTRY =====
def engine():
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
                if price <= 0:
                    continue

                direction = decide(sym)
                if not direction:
                    continue

                with lock:

                    lev = 10

                    try: exchange.set_margin_mode("cross", sym)
                    except: pass

                    try: exchange.set_leverage(lev, sym)
                    except: pass

                    qty = (5 * lev) / price
                    qty = float(exchange.amount_to_precision(sym, qty))

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction=="long" else "sell",
                        qty
                    ))

                    trade_state[sym] = {
                        "direction": direction,
                        "entry": price,
                        "tp1": False,
                        "step": 0,
                        "trail_active": False,
                        "trail_price": price,
                        "closing": False
                    }

                    active_trades.add(sym)
                    bot.send_message(CHAT_ID, f"🚀 {sym} {direction}")
                    break

            time.sleep(5)

        except Exception as e:
            print("ENGINE ERROR:", e)
            time.sleep(5)

# ===== MANAGE =====
def manage():
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

                st = trade_state[sym]

                if st.get("closing"):
                    continue

                direction = "long" if p["side"] == "long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])
                entry = st["entry"]
                pnl = safe(p.get("unrealizedPnl"))

                # ===== TP1 =====
                if not st["tp1"] and pnl >= TP1_USDT:
                    part = qty * 0.4

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        part,
                        params={"reduceOnly": True}
                    ))

                    st["tp1"] = True
                    st["sl"] = entry
                    st["trail_active"] = True
                    st["trail_price"] = price

                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # ===== STEP =====
                profit_pct = abs(price - entry) / entry

                if profit_pct > 0.01 and st["step"] < 1:
                    st["step"] = 1
                    st["sl"] = entry

                if profit_pct > 0.02 and st["step"] < 2:
                    st["step"] = 2
                    st["sl"] = entry * (1.01 if direction=="long" else 0.99)

                # ===== TRAILING =====
                if st["trail_active"]:

                    if direction == "long":
                        if price > st["trail_price"]:
                            st["trail_price"] = price

                        if price <= st["trail_price"] * (1 - TRAIL_GAP):
                            st["closing"] = True

                            safe_api(lambda: exchange.create_market_order(
                                sym, "sell", qty,
                                params={"reduceOnly": True}
                            ))

                            active_trades.discard(sym)
                            trade_state.pop(sym, None)

                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")

                    else:
                        if price < st["trail_price"]:
                            st["trail_price"] = price

                        if price >= st["trail_price"] * (1 + TRAIL_GAP):
                            st["closing"] = True

                            safe_api(lambda: exchange.create_market_order(
                                sym, "buy", qty,
                                params={"reduceOnly": True}
                            ))

                            active_trades.discard(sym)
                            trade_state.pop(sym, None)

                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")

                # ===== HARD STOP =====
                if pnl < -0.5:
                    st["closing"] = True

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    ))

                    active_trades.discard(sym)
                    trade_state.pop(sym, None)

                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")

            time.sleep(3)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()
time.sleep(1)

load_open_positions()

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 STABLE BOT AKTİF")
bot.infinity_polling()
