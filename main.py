import os
import time
import telebot
import ccxt
import threading

# ===== TELEGRAM =====
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASS')

bot = telebot.TeleBot(TELE_TOKEN)

# ===== AYAR =====
MARGIN = 3
LEV = 5              # 10 yerine 5 (10 çok agresif)
MAX_POS = 1

STOP_PERCENT = 0.01  # %1 fiyat stop

BANNED = ['BTC','ETH','XRP','SOL']

exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

profits = {}
lock_levels = {}
lock = threading.Lock()

def safe(x):
    try:
        return float(x)
    except:
        return 0.0


# ===== POZİSYON VAR MI =====
def has_position():
    positions = exchange.fetch_positions()
    return [p for p in positions if safe(p.get('contracts')) > 0]


# ===== OPEN =====
def open_trade(sym, side):
    try:
        if has_position():
            return False

        exchange.set_leverage(LEV, sym)

        price = safe(exchange.fetch_ticker(sym)['last'])
        qty = (MARGIN * LEV) / price
        qty = float(exchange.amount_to_precision(sym, qty))

        order_side = "buy" if side == "long" else "sell"

        exchange.create_market_order(
            sym,
            order_side,
            qty
        )

        with lock:
            profits[sym] = 0
            lock_levels[sym] = 0

        bot.send_message(MY_CHAT_ID, f"{sym} {side.upper()} AÇILDI")
        return True

    except Exception as e:
        print("OPEN ERROR:", e)
        return False


# ===== MANAGER =====
def manager():
    while True:
        try:
            positions = has_position()

            for p in positions:
                sym = p['symbol']
                side = p['side']
                qty = safe(p.get('contracts'))
                entry = safe(p.get('entryPrice'))
                last = safe(exchange.fetch_ticker(sym)['last'])

                # FİYAT BAZLI STOP
                if side == "long":
                    stop_price = entry * (1 - STOP_PERCENT)
                    profit = (last - entry) * qty
                    exit_side = "sell"
                else:
                    stop_price = entry * (1 + STOP_PERCENT)
                    profit = (entry - last) * qty
                    exit_side = "buy"

                # HARD STOP
                if (side == "long" and last <= stop_price) or \
                   (side == "short" and last >= stop_price):

                    exchange.create_market_order(
                        sym,
                        exit_side,
                        qty,
                        params={'reduceOnly': True}
                    )

                    profits.pop(sym, None)
                    lock_levels.pop(sym, None)
                    bot.send_message(MY_CHAT_ID, "STOP ❌")
                    continue

                # PROFIT TAKİP
                with lock:
                    if profit > profits.get(sym, 0):
                        profits[sym] = profit

                    peak = profits.get(sym, 0)
                    locked = lock_levels.get(sym, 0)

                # LOCK SİSTEMİ
                if peak >= 1.0 and locked < 1.0:
                    lock_levels[sym] = 1.0
                if peak >= 2.0 and locked < 2.0:
                    lock_levels[sym] = 2.0

                locked = lock_levels.get(sym, 0)

                if locked > 0 and profit <= locked:
                    exchange.create_market_order(
                        sym,
                        exit_side,
                        qty,
                        params={'reduceOnly': True}
                    )

                    profits.pop(sym, None)
                    lock_levels.pop(sym, None)
                    bot.send_message(MY_CHAT_ID, "LOCK EXIT ✅")

            time.sleep(3)

        except Exception as e:
            print("MANAGER ERROR:", e)
            time.sleep(3)


# ===== SCANNER =====
def scanner():
    markets = exchange.load_markets()

    while True:
        try:
            if has_position():
                time.sleep(10)
                continue

            for m in markets.values():
                sym = m['symbol']

                if ':USDT' not in sym:
                    continue
                if any(x in sym for x in BANNED):
                    continue

                candles = exchange.fetch_ohlcv(sym,'5m',limit=30)
                closes = [c[4] for c in candles]

                ema9 = sum(closes[-9:])/9
                ema21 = sum(closes[-21:])/21

                if ema9 > ema21 and closes[-1] > closes[-2]:
                    if open_trade(sym,"long"):
                        break

                if ema9 < ema21 and closes[-1] < closes[-2]:
                    if open_trade(sym,"short"):
                        break

                time.sleep(0.2)

            time.sleep(12)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(12)


@bot.message_handler(func=lambda m: True)
def stop(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID):
        return
    if msg.text.lower()=="dur":
        os._exit(0)


if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"SCALP LOCK ENGINE AKTİF")
    bot.infinity_polling()
