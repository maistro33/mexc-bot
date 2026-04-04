import os
import time
import ccxt
import telebot
import threading
import pandas as pd

# ===== ENV CHECK =====
REQUIRED_ENV = [
    "TELE_TOKEN",
    "MY_CHAT_ID",
    "BITGET_API",
    "BITGET_SEC",
    "BITGET_PASS"
]

for key in REQUIRED_ENV:
    if not os.getenv(key):
        raise Exception(f"❌ Missing ENV: {key}")

# ===== SETTINGS =====
AGGR_VOLUME = 200_000
TOP_COINS = 50
MAX_TRADES = 2

TP1_USDT = 0.25
TRAIL_GAP = 0.01

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

exchange.load_markets()

# ===== GLOBAL =====
active_trades = set()
trade_state = {}
ai_data = []
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

# ===== ORDERBOOK =====
def orderbook(sym):
    ob = safe_api(lambda: exchange.fetch_order_book(sym, 5))
    if not ob:
        return 0
    bids = sum(b[1] for b in ob["bids"])
    asks = sum(a[1] for a in ob["asks"])
    return (bids - asks)/(bids + asks) if bids+asks else 0

# ===== DECISION =====
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

# ===== ENGINE =====
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

                # TP1
                if not st["tp1"] and pnl >= TP1_USDT:
                    part = qty * 0.4

                    safe_api(lambda: exchange.create_market_order(
                        sym,
                        "sell" if direction=="long" else "buy",
                        part,
                        params={"reduceOnly": True}
                    ))

                    st["tp1"] = True
                    st["trail_active"] = True
                    st["trail_price"] = price

                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TRAILING
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

                            bot.send_message(CHAT_ID, f"🔒 EXIT {sym}")

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

                            bot.send_message(CHAT_ID, f"🔒 EXIT {sym}")

                # HARD STOP (%2)
                loss_pct = abs(price - entry) / entry
                if loss_pct >= 0.02:
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

# ===== AI DATA COLLECTOR =====
def collect_ai_data():
    while True:
        try:
            symbols = get_symbols()[:5]

            for sym in symbols:
                try:
                    ohlcv = exchange.fetch_ohlcv(sym, "5m", limit=1)
                    if not ohlcv:
                        continue

                    timestamp, open_, high, low, close, volume = ohlcv[0]
                    ob = orderbook(sym)
                    volatility = (high - low) / close if close else 0

                    ai_data.append({
                        "symbol": sym,
                        "time": timestamp,
                        "open": open_,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                        "orderbook": ob,
                        "volatility": volatility
                    })

                    print("AI DATA:", sym)
                    time.sleep(0.2)

                except Exception as e:
                    print("AI ERROR:", e)

            if len(ai_data) >= 100:
                df = pd.DataFrame(ai_data)
                df.to_csv("ai_live_data.csv", index=False)
                print("💾 AI DATA SAVED:", len(df))

            time.sleep(15)

        except Exception as e:
            print("AI COLLECT ERROR:", e)
            time.sleep(5)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=collect_ai_data, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 Sadik Bot v1.5 AI AKTİF")
bot.infinity_polling()
