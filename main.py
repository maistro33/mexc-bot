import os
import time
import ccxt
import telebot
import threading

# ===== SETTINGS =====
SAFE_VOLUME = 2_000_000
SAFE_LEV = 10
SAFE_MARGIN = 5

TOP_COINS = 100
BUFFER_PCT = 0.0015

TP_SPLIT = [0.4, 0.3, 0.3]

TRAIL_START = 0.01
TRAIL_GAP = 0.015

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

# ===== 🔥 FIXED POSITION CHECK =====
def has_position():
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            qty = safe(p.get("contracts"))
            if qty is not None and qty > 0:
                print("ACTIVE POSITION:", p["symbol"], qty)
                return True
        return False
    except Exception as e:
        print("POS ERROR:", e)
        return False

# ===== 🔥 SIMPLE SHORT SYSTEM =====
def short_pullback_entry(sym):
    m5 = get_candles(sym, "5m", 20)
    if len(m5) < 10:
        return None

    closes = [c[4] for c in m5]

    # düşüş var mı
    if closes[-1] > closes[-5]:
        return None

    prev = m5[-2]
    last = m5[-1]

    # yeşil → kırmızı
    if prev[4] > prev[1] and last[4] < last[1]:
        entry = last[4]
        highs = [c[2] for c in m5[-10:]]
        sl = max(highs) * (1 + BUFFER_PCT)

        return {"entry": entry, "sl": sl}

    return None

# ===== MARKET =====
def get_symbols(volume):
    try:
        tickers = exchange.fetch_tickers()
        result = []

        for sym, data in tickers.items():
            if ":USDT" not in sym:
                continue

            vol = safe(data.get("quoteVolume"))
            if vol >= volume:
                result.append(sym)

        return result[:TOP_COINS]

    except Exception as e:
        print("SYMBOL ERROR:", e)
        return []

# ===== STATE =====
trade_state = {}

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
                direction = "long" if side == "long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])
                pnl = safe(p.get("unrealizedPnl"))

                st = trade_state[sym]
                sl = st["sl"]

                TP_USDT = 1.0

                # STOP
                if (direction == "long" and price <= sl) or (direction == "short" and price >= sl):
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", qty, params={"reduceOnly": True})
                    trade_state.pop(sym, None)
                    bot.send_message(CHAT_ID, f"❌ STOP {sym}")
                    continue

                # TP1
                if not st["tp1"] and pnl >= TP_USDT:
                    exchange.create_market_order(sym, "sell" if direction == "long" else "buy", qty * TP_SPLIT[0], params={"reduceOnly": True})
                    st["tp1"] = True
                    st["sl"] = entry
                    st["trail_active"] = True
                    st["trail_price"] = price
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # TRAILING
                if st.get("trail_active"):
                    if direction == "long":
                        if price > st["trail_price"]:
                            st["trail_price"] = price
                        if (price - entry)/entry > TRAIL_START:
                            st["trail_started"] = True
                        if st["trail_started"] and price <= st["trail_price"] * (1 - TRAIL_GAP):
                            exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")
                    else:
                        if price < st["trail_price"]:
                            st["trail_price"] = price
                        if (entry - price)/entry > TRAIL_START:
                            st["trail_started"] = True
                        if st["trail_started"] and price >= st["trail_price"] * (1 + TRAIL_GAP):
                            exchange.create_market_order(sym, "buy", qty, params={"reduceOnly": True})
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🔒 TRAIL EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)

# ===== ENTRY =====
def run():
    while True:
        try:
            print("RUNNING SCAN...")

            if has_position():
                print("POSITION VAR - BEKLIYOR")
                time.sleep(5)
                continue

            symbols = get_symbols(SAFE_VOLUME)

            for sym in symbols:
                print("SCAN:", sym)

                pb = short_pullback_entry(sym)

                if not pb:
                    continue

                print("ENTRY FOUND:", sym)

                price = safe(exchange.fetch_ticker(sym)["last"])
                qty = (SAFE_MARGIN * SAFE_LEV) / price
                qty = float(exchange.amount_to_precision(sym, qty))

                exchange.set_leverage(SAFE_LEV, sym)
                exchange.create_market_order(sym, "sell", qty)

                trade_state[sym] = {
                    "sl": pb["sl"],
                    "tp1": False,
                    "trail_active": False,
                    "trail_price": 0,
                    "trail_started": False
                }

                bot.send_message(CHAT_ID, f"💣 SHORT {sym}")
                break

            time.sleep(5)

        except Exception as e:
            print("RUN ERROR:", e)

# ===== START =====
exchange.fetch_balance()
bot.remove_webhook()

threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()
threading.Thread(target=bot.infinity_polling, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 BOT FIXED & AKTİF")
