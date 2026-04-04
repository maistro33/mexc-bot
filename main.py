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
memory = {}

lock = threading.Lock()

current_margin = 5

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

# ===== TEST DECIDE (GARANTİ TRADE) =====
def decide(sym):
    try:
        m5 = safe_api(lambda: exchange.fetch_ohlcv(sym, "5m", 20))
        if not m5 or len(m5) < 10:
            return None, 0, {}

        closes = [x[4] for x in m5 if len(x) > 5]

        if len(closes) < 5:
            return None, 0, {}

        # 🔥 BASİT MANTIK (HER ZAMAN SİNYAL)
        if closes[-1] > closes[-3]:
            direction = "long"
        else:
            direction = "short"

        return direction, 1.5, {}

    except Exception as e:
        print("DECIDE ERROR:", e)
        return None, 0, {}

# ===== EXIT =====
def exit_check(sym, pnl, direction, open_time):
    if time.time() - open_time < 120:
        return False

    if pnl < -1 or pnl > 2:
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

                if time.time() - last_trade_time.get(sym, 0) < 10:
                    continue

                ticker = safe_api(lambda: exchange.fetch_ticker(sym))
                if not ticker:
                    continue

                price = safe(ticker.get("last"))
                if price <= 0:
                    continue

                direction, score, _ = decide(sym)

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

                    qty = max((current_margin * lev) / price, min_q)
                    qty = float(exchange.amount_to_precision(sym, qty))

                    order = safe_api(lambda: exchange.create_market_order(
                        sym,
                        "buy" if direction == "long" else "sell",
                        qty,
                        params={"marginMode": "cross"}
                    ))

                    if not order:
                        continue

                    trade_state[sym] = {
                        "dir": direction,
                        "time": time.time()
                    }

                    active_trades.add(sym)
                    last_trade_time[sym] = time.time()

                    bot.send_message(CHAT_ID, f"🚀 TEST TRADE: {sym} {direction}")
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

                    bot.send_message(CHAT_ID, f"❌ TEST EXIT: {sym} {round(pnl,2)}")

            time.sleep(6)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)

# ===== START =====
bot.remove_webhook()
time.sleep(1)

threading.Thread(target=engine, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 TEST BOT AKTİF (GARANTİ TRADE)")
bot.infinity_polling()
