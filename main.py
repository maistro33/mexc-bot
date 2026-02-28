import os
import time
import ccxt
import telebot
import threading

# =====================
# ===== AYARLAR =======
# =====================

LEV = 10
MARGIN = 10
MAX_POS = 1

TP_SPLIT = [0.4, 0.3, 0.3]  # TP1, TP2, TP3

# =====================
# ===== TELEGRAM ======
# =====================

TELE_TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
bot = telebot.TeleBot(TELE_TOKEN)

# =====================
# ===== BITGET ========
# =====================

API_KEY = os.getenv("BITGET_API")
API_SEC = os.getenv("BITGET_SEC")
PASSPHRASE = "Berfin33"

exchange = ccxt.bitget({
    "apiKey": API_KEY,
    "secret": API_SEC,
    "password": PASSPHRASE,
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
    "timeout": 30000
})

# =====================
# ===== YARDIMCI ======
# =====================

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def get_candles(sym, tf, limit=100):
    return exchange.fetch_ohlcv(sym, tf, limit=limit)

def has_position():
    positions = exchange.fetch_positions()
    active = [p for p in positions if safe(p.get("contracts")) > 0]
    return len(active) > 0

# =====================
# ===== YÖN ======
# =====================

def get_direction(sym):
    try:
        d = get_candles(sym, "1d", 50)
        h4 = get_candles(sym, "4h", 50)

        d_high = [c[2] for c in d]
        d_low  = [c[3] for c in d]

        h_high = [c[2] for c in h4]
        h_low  = [c[3] for c in h4]

        daily_long = d_high[-1] > d_high[-2] and d_low[-1] > d_low[-2]
        daily_short = d_high[-1] < d_high[-2] and d_low[-1] < d_low[-2]

        h4_long = h_high[-1] > h_high[-2] and h_low[-1] > h_low[-2]
        h4_short = h_high[-1] < h_high[-2] and h_low[-1] < h_low[-2]

        if daily_long and h4_long:
            return "long"
        if daily_short and h4_short:
            return "short"

        return None

    except:
        return None

# =====================
# ===== LİKİDİTE ======
# =====================

def liquidity_sweep(sym, direction):
    try:
        h1 = get_candles(sym, "1h", 30)
        highs = [c[2] for c in h1]
        lows = [c[3] for c in h1]

        if direction == "long":
            return lows[-1] < min(lows[:-2])
        else:
            return highs[-1] > max(highs[:-2])

    except:
        return False

# =====================
# ===== ENTRY MODEL ===
# =====================

def entry_model(sym, direction):
    try:
        m15 = get_candles(sym, "15m", 50)

        o = [c[1] for c in m15]
        h = [c[2] for c in m15]
        l = [c[3] for c in m15]
        c_ = [c[4] for c in m15]

        body = abs(c_[-1] - o[-1])
        avg_body = sum(abs(c_[i] - o[i]) for i in range(-10, -1)) / 9

        # Displacement
        if body < avg_body * 1.5:
            return None

        # BOS
        if direction == "long":
            if c_[-1] <= max(h[-5:-1]):
                return None
        else:
            if c_[-1] >= min(l[-5:-1]):
                return None

        # FVG
        if direction == "long":
            if h[-3] < l[-1]:
                entry = (h[-3] + l[-1]) / 2
                sl = l[-2]
                return {"entry": entry, "sl": sl}
        else:
            if l[-3] > h[-1]:
                entry = (l[-3] + h[-1]) / 2
                sl = h[-2]
                return {"entry": entry, "sl": sl}

        return None

    except:
        return None

# =====================
# ===== EMİR ==========
# =====================

def place_trade(sym, direction, setup):
    try:
        exchange.set_leverage(LEV, sym)

        ticker = exchange.fetch_ticker(sym)
        price = safe(ticker["last"])

        notional = MARGIN * LEV
        qty = notional / price
        qty = float(exchange.amount_to_precision(sym, qty))

        side = "buy" if direction == "long" else "sell"

        exchange.create_market_order(sym, side, qty)

        entry_price = price
        sl = setup["sl"]
        risk = abs(entry_price - sl)

        tp1 = entry_price + risk if direction == "long" else entry_price - risk
        tp2 = entry_price + 2*risk if direction == "long" else entry_price - 2*risk
        tp3 = entry_price + 3*risk if direction == "long" else entry_price - 3*risk

        bot.send_message(
            CHAT_ID,
            f"{sym} {direction.upper()} AÇILDI\n"
            f"Entry: {entry_price}\n"
            f"SL: {sl}\n"
            f"TP1: {tp1}\n"
            f"TP2: {tp2}\n"
            f"TP3: {tp3}"
        )

    except Exception as e:
        bot.send_message(CHAT_ID, f"Emir Hata: {e}")

# =====================
# ===== ANA LOOP ======
# =====================

def run():
    markets = exchange.load_markets()
    symbols = [s for s in markets if ":USDT" in s]

    while True:
        try:
            if has_position():
                time.sleep(20)
                continue

            for sym in symbols:
                try:
                    direction = get_direction(sym)
                    if not direction:
                        continue

                    if not liquidity_sweep(sym, direction):
                        continue

                    setup = entry_model(sym, direction)
                    if not setup:
                        continue

                    place_trade(sym, direction, setup)
                    time.sleep(60)

                except:
                    continue

            time.sleep(30)

        except:
            time.sleep(30)

# =====================
# ===== START =========
# =====================

try:
    exchange.fetch_balance()
    print("Bitget bağlantı OK")
except Exception as e:
    print("Bağlantı Hatası:", e)

threading.Thread(target=run, daemon=True).start()
bot.send_message(CHAT_ID, "SMART MONEY SNIPER BOT AKTİF")
bot.infinity_polling()
