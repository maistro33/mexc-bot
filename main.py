import os
import time
import ccxt
import telebot
import threading

# ===== TELEGRAM =====
TELE_TOKEN = os.getenv("TELE_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
bot = telebot.TeleBot(TELE_TOKEN)

# ===== API =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS") or "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

# ===== AYAR =====
LEVERAGE = 5
MARGIN = 3
STOP_PERCENT = 0.01
TP_PERCENT = 0.02
MIN_24H_CHANGE = 4
MIN_VOLUME = 3_000_000

# MAJOR COINLERİ DIŞLA
MAJORS = [
    "BTC","ETH","BNB","SOL","XRP","ADA","DOGE",
    "AVAX","DOT","LINK","LTC","BCH","ATOM"
]

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def ema(data, period):
    k = 2 / (period + 1)
    ema_val = data[0]
    for price in data[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

def rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_position():
    positions = exchange.fetch_positions()
    for p in positions:
        if safe(p.get("contracts")) > 0:
            return p
    return None

def open_trade(symbol, side):
    exchange.set_leverage(LEVERAGE, symbol)
    price = safe(exchange.fetch_ticker(symbol)["last"])
    qty = (MARGIN * LEVERAGE) / price
    qty = float(exchange.amount_to_precision(symbol, qty))

    exchange.create_market_order(
        symbol,
        "buy" if side == "long" else "sell",
        qty
    )

    bot.send_message(MY_CHAT_ID, f"{symbol} {side.upper()} AÇILDI")

def manager():
    while True:
        try:
            pos = get_position()
            if not pos:
                time.sleep(3)
                continue

            symbol = pos["symbol"]
            side = pos["side"]
            entry = safe(pos["entryPrice"])
            qty = safe(pos["contracts"])
            price = safe(exchange.fetch_ticker(symbol)["last"])

            if side == "long":
                stop = entry * (1 - STOP_PERCENT)
                tp = entry * (1 + TP_PERCENT)
                exit_side = "sell"
            else:
                stop = entry * (1 + STOP_PERCENT)
                tp = entry * (1 - TP_PERCENT)
                exit_side = "buy"

            if (side == "long" and price <= stop) or \
               (side == "short" and price >= stop):

                exchange.create_market_order(
                    symbol, exit_side, qty,
                    params={"reduceOnly": True}
                )
                bot.send_message(MY_CHAT_ID, "STOP ❌")

            elif (side == "long" and price >= tp) or \
                 (side == "short" and price <= tp):

                exchange.create_market_order(
                    symbol, exit_side, qty,
                    params={"reduceOnly": True}
                )
                bot.send_message(MY_CHAT_ID, "TP ✅")

            time.sleep(3)

        except Exception as e:
            print("MANAGER ERROR:", e)
            time.sleep(3)

def scanner():
    markets = exchange.load_markets()

    while True:
        try:
            if get_position():
                time.sleep(10)
                continue

            for symbol in markets:
                if ":USDT" not in symbol:
                    continue

                if any(m in symbol for m in MAJORS):
                    continue

                ticker = exchange.fetch_ticker(symbol)
                change = safe(ticker.get("percentage"))
                volume = safe(ticker.get("quoteVolume"))

                if abs(change) < MIN_24H_CHANGE:
                    continue

                if volume < MIN_VOLUME:
                    continue

                candles = exchange.fetch_ohlcv(symbol, "5m", limit=50)
                closes = [c[4] for c in candles]

                ema20 = ema(closes[-20:], 20)
                ema50 = ema(closes[-50:], 50)
                rsi_val = rsi(closes)

                last_close = closes[-1]

                # LONG MOMENTUM
                if change > 0 and ema20 > ema50 and rsi_val > 55:
                    open_trade(symbol, "long")
                    break

                # SHORT MOMENTUM
                if change < 0 and ema20 < ema50 and rsi_val < 45:
                    open_trade(symbol, "short")
                    break

                time.sleep(0.2)

            time.sleep(20)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(10)

@bot.message_handler(func=lambda m: True)
def stop(msg):
    if str(msg.chat.id) != str(MY_CHAT_ID):
        return
    if msg.text.lower() == "dur":
        os._exit(0)

if __name__ == "__main__":
    threading.Thread(target=manager, daemon=True).start()
    threading.Thread(target=scanner, daemon=True).start()
    bot.send_message(MY_CHAT_ID, "MEME MOMENTUM BOT AKTİF")
    bot.infinity_polling()
