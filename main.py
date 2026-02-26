import os
import time
import ccxt
import threading
import telebot
import numpy as np

# ===== TELEGRAM =====
TELE_TOKEN = os.getenv("TELE_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

bot = telebot.TeleBot(TELE_TOKEN)

# ===== API =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

# ===== AYAR =====
LEVERAGE = 5
RISK_PERCENT = 0.20   # Bakiyenin %20'si
STOP_PERCENT = 0.01   # %1 fiyat stop
TP_PERCENT = 0.02     # %2 TP
MAX_LOSS_STREAK = 2

loss_streak = 0
active_symbol = None


# ===== EMA =====
def ema(data, period):
    k = 2 / (period + 1)
    ema_val = data[0]
    for price in data[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


# ===== RSI =====
def rsi(data, period=14):
    deltas = np.diff(data)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ===== POZİSYON KONTROL =====
def get_position():
    positions = exchange.fetch_positions()
    for p in positions:
        if float(p["contracts"]) > 0:
            return p
    return None


# ===== POZİSYON AÇ =====
def open_trade(symbol, side):
    global active_symbol

    balance = exchange.fetch_balance()
    usdt = balance["USDT"]["free"]

    margin = usdt * RISK_PERCENT
    price = exchange.fetch_ticker(symbol)["last"]

    qty = (margin * LEVERAGE) / price
    qty = float(exchange.amount_to_precision(symbol, qty))

    exchange.set_leverage(LEVERAGE, symbol)

    exchange.create_market_order(
        symbol,
        "buy" if side == "long" else "sell",
        qty
    )

    active_symbol = symbol
    bot.send_message(MY_CHAT_ID, f"{symbol} {side.upper()} açıldı")


# ===== MANAGER =====
def manager():
    global loss_streak, active_symbol

    while True:
        try:
            pos = get_position()
            if not pos:
                time.sleep(2)
                continue

            symbol = pos["symbol"]
            side = pos["side"]
            entry = float(pos["entryPrice"])
            qty = float(pos["contracts"])
            price = exchange.fetch_ticker(symbol)["last"]

            # Stop ve TP fiyatı
            if side == "long":
                stop_price = entry * (1 - STOP_PERCENT)
                tp_price = entry * (1 + TP_PERCENT)
                exit_side = "sell"
            else:
                stop_price = entry * (1 + STOP_PERCENT)
                tp_price = entry * (1 - TP_PERCENT)
                exit_side = "buy"

            # STOP
            if (side == "long" and price <= stop_price) or \
               (side == "short" and price >= stop_price):

                exchange.create_market_order(
                    symbol, exit_side, qty,
                    params={"reduceOnly": True}
                )

                loss_streak += 1
                bot.send_message(MY_CHAT_ID, "STOP ❌")
                active_symbol = None

            # TAKE PROFIT
            elif (side == "long" and price >= tp_price) or \
                 (side == "short" and price <= tp_price):

                exchange.create_market_order(
                    symbol, exit_side, qty,
                    params={"reduceOnly": True}
                )

                loss_streak = 0
                bot.send_message(MY_CHAT_ID, "TP ✅")
                active_symbol = None

            if loss_streak >= MAX_LOSS_STREAK:
                bot.send_message(MY_CHAT_ID, "2 ZARAR → BOT DURDU")
                os._exit(0)

            time.sleep(2)

        except Exception as e:
            print("MANAGER ERROR:", e)
            time.sleep(2)


# ===== SCANNER =====
def scanner():
    global active_symbol

    markets = exchange.load_markets()

    while True:
        try:
            if get_position() is not None:
                time.sleep(5)
                continue

            for m in markets.values():
                symbol = m["symbol"]

                if ":USDT" not in symbol:
                    continue

                candles = exchange.fetch_ohlcv(symbol, "5m", limit=50)
                closes = np.array([c[4] for c in candles])

                ema20 = ema(closes[-20:], 20)
                ema50 = ema(closes[-50:], 50)
                rsi_val = rsi(closes)

                # LONG
                if ema20 > ema50 and rsi_val > 55:
                    open_trade(symbol, "long")
                    break

                # SHORT
                if ema20 < ema50 and rsi_val < 45:
                    open_trade(symbol, "short")
                    break

                time.sleep(0.2)

            time.sleep(10)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=manager, daemon=True).start()
    threading.Thread(target=scanner, daemon=True).start()
    bot.send_message(MY_CHAT_ID, "AGRESİF BOT AKTİF")
    bot.infinity_polling()
