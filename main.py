import os
import time
import ccxt
import telebot
import threading
from datetime import datetime

# =====================
# ENV
# =====================

TELE_TOKEN = os.getenv("TELE_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
API_KEY = os.getenv("BITGET_API")
API_SEC = os.getenv("BITGET_SEC")
PASSPHRASE = os.getenv("BITGET_PASS")

bot = telebot.TeleBot(TELE_TOKEN)

# =====================
# EXCHANGE
# =====================

exchange = ccxt.bitget({
    "apiKey": API_KEY,
    "secret": API_SEC,
    "password": PASSPHRASE,
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

# =====================
# AYARLAR
# =====================

MARGIN = 2.5
LEVERAGE = 10
MAX_POS = 2

STOP_PERCENT = 0.6
TRAIL_START = 1.5
TRAIL_GAP = 0.7

DAILY_MAX_LOSS = 2
MIN_VOLUME = 6_000_000
MAX_SPREAD = 0.15

BANNED = ["BTC","ETH","BNB","SOL"]

highest = {}
daily_loss = 0
current_day = datetime.utcnow().day

# =====================
# YARDIMCI
# =====================

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def ema(data, period):
    k = 2 / (period + 1)
    e = data[0]
    for p in data[1:]:
        e = p * k + e * (1 - k)
    return e

# =====================
# BTC TREND
# =====================

def btc_trend():
    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT", "5m", limit=60)
        closes = [c[4] for c in candles]
        return ema(closes, 20) > ema(closes, 50)
    except:
        return None

# =====================
# EMİR AÇMA
# =====================

def open_trade(symbol, side):
    try:
        positions = exchange.fetch_positions()
        active = [p for p in positions if safe(p.get("contracts")) > 0]

        if len(active) >= MAX_POS:
            return

        if any(p["symbol"] == symbol for p in active):
            return

        ticker = exchange.fetch_ticker(symbol)
        spread = (ticker["ask"] - ticker["bid"]) / ticker["last"] * 100

        if spread > MAX_SPREAD:
            return

        price = ticker["last"]
        qty = (MARGIN * LEVERAGE) / price
        qty = float(exchange.amount_to_precision(symbol, qty))

        exchange.set_leverage(LEVERAGE, symbol)

        exchange.create_market_order(
            symbol,
            "buy" if side == "long" else "sell",
            qty
        )

        highest[symbol] = 0

        bot.send_message(
            MY_CHAT_ID,
            f"🚀 {symbol} {side.upper()} | 10x"
        )

    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"HATA: {e}")

# =====================
# POZİSYON YÖNETİMİ
# =====================

def manager():
    global daily_loss, current_day

    while True:
        try:
            # Gün değişimi reset
            if datetime.utcnow().day != current_day:
                daily_loss = 0
                current_day = datetime.utcnow().day

            positions = exchange.fetch_positions()

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                side = p["side"]
                entry = safe(p["entryPrice"])
                last = safe(exchange.fetch_ticker(sym)["last"])

                pnl = (
                    (last - entry) / entry * 100
                    if side == "long"
                    else (entry - last) / entry * 100
                )

                # STOP
                if pnl <= -STOP_PERCENT:
                    exchange.create_market_order(
                        sym,
                        "sell" if side == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )
                    daily_loss += 1
                    highest.pop(sym, None)
                    continue

                # En yüksek kârı takip et
                if pnl > highest.get(sym, 0):
                    highest[sym] = pnl

                # TRAILING
                if highest.get(sym, 0) >= TRAIL_START and \
                   highest[sym] - pnl >= TRAIL_GAP:

                    exchange.create_market_order(
                        sym,
                        "sell" if side == "long" else "buy",
                        qty,
                        params={"reduceOnly": True}
                    )
                    highest.pop(sym, None)

            time.sleep(2)

        except:
            time.sleep(3)

# =====================
# MARKET TARAMA
# =====================

def scanner():
    while True:
        try:
            if daily_loss >= DAILY_MAX_LOSS:
                time.sleep(60)
                continue

            trend = btc_trend()
            if trend is None:
                time.sleep(5)
                continue

            tickers = exchange.fetch_tickers()

            markets = sorted(
                [t for t in tickers.values() if ":USDT" in t["symbol"]],
                key=lambda x: x.get("quoteVolume", 0),
                reverse=True
            )[5:25]

            for m in markets:
                symbol = m["symbol"]

                if any(b in symbol for b in BANNED):
                    continue

                if m.get("quoteVolume", 0) < MIN_VOLUME:
                    continue

                candles = exchange.fetch_ohlcv(symbol, "5m", limit=40)
                closes = [c[4] for c in candles]

                ema9 = ema(closes, 9)
                ema21 = ema(closes, 21)

                if trend and ema9 > ema21:
                    open_trade(symbol, "long")

                if not trend and ema9 < ema21:
                    open_trade(symbol, "short")

            time.sleep(6)

        except:
            time.sleep(5)

# =====================
# TELEGRAM
# =====================

@bot.message_handler(func=lambda m: True)
def handle(msg):
    if str(msg.chat.id) != str(MY_CHAT_ID):
        return

    if msg.text.lower() == "dur":
        bot.send_message(MY_CHAT_ID, "Bot durduruldu.")
        os._exit(0)

# =====================
# START
# =====================

if __name__ == "__main__":
    threading.Thread(target=manager, daemon=True).start()
    threading.Thread(target=scanner, daemon=True).start()
    bot.send_message(MY_CHAT_ID, "🚀 TREND TAŞIYAN 10X AKTİF")
    bot.infinity_polling()
