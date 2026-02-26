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
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TELE_TOKEN)

# ===== AYAR =====
MARGIN = 3
LEV = 10
MAX_POS = 3

FIXED_STOP = 0.45          # Sert zarar durdur
MIN_VOLUME = 200000       # Minimum 24h hacim
MIN_VOLATILITY = 1.5      # Minimum % hareket (pump yakalamak için)

BANNED = [
    'BTC','ETH','XRP','SOL',
    'BCH','LTC','ADA','DOT',
    'LINK','BNB','AVAX'
]

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

# ===== OPEN =====
def open_trade(sym, side):
    try:
        positions = [p for p in exchange.fetch_positions()
                     if safe(p.get('contracts')) > 0]

        if len(positions) >= MAX_POS:
            return False

        exchange.set_leverage(LEV, sym)

        price = safe(exchange.fetch_ticker(sym)['last'])
        qty = (MARGIN * LEV) / price
        qty = float(exchange.amount_to_precision(sym, qty))

        exchange.create_market_order(
            sym,
            "buy" if side=="long" else "sell",
            qty
        )

        with lock:
            profits[sym] = 0
            lock_levels[sym] = 0

        bot.send_message(MY_CHAT_ID, f"🎯 {sym} {side.upper()}")
        return True

    except Exception as e:
        print("OPEN ERROR:", e)
        return False

# ===== MANAGER =====
def manager():
    while True:
        try:
            positions = [p for p in exchange.fetch_positions()
                         if safe(p.get('contracts')) > 0]

            for p in positions:
                sym = p['symbol']
                side = p['side']
                qty = safe(p.get('contracts'))
                entry = safe(p.get('entryPrice'))
                last = safe(exchange.fetch_ticker(sym)['last'])

                profit = (last-entry)*qty if side=="long" else (entry-last)*qty

                with lock:
                    if profit > profits.get(sym, 0):
                        profits[sym] = profit

                    peak = profits.get(sym, 0)
                    locked = lock_levels.get(sym, 0)

                # ===== HARD STOP =====
                if profit <= -FIXED_STOP:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)
                    lock_levels.pop(sym,None)
                    continue

                # ===== TRAILING LOCK SİSTEMİ =====

                # 0.40 USDT üstü break-even aktif
                if peak >= 0.40 and locked < 0:
                    lock_levels[sym] = 0

                # 1 USDT kilitle
                if peak >= 1.0 and locked < 1.0:
                    lock_levels[sym] = 1.0

                # 1.5 USDT kilitle
                if peak >= 1.5 and locked < 1.5:
                    lock_levels[sym] = 1.5

                # 2 USDT kilitle
                if peak >= 2.0 and locked < 2.0:
                    lock_levels[sym] = 2.0

                locked = lock_levels.get(sym, 0)

                # ===== EXIT IF PROFIT DÜŞERSE =====
                if locked > 0 and profit <= locked:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)
                    lock_levels.pop(sym,None)

            time.sleep(3)

        except Exception as e:
            print("MANAGER ERROR:", e)
            time.sleep(3)

# ===== SCANNER =====
def scanner():
    markets = exchange.load_markets()

    while True:
        try:
            positions = [p for p in exchange.fetch_positions()
                         if safe(p.get('contracts')) > 0]

            if len(positions) >= MAX_POS:
                time.sleep(8)
                continue

            for m in markets.values():
                sym = m['symbol']

                if ':USDT' not in sym:
                    continue

                if any(x in sym for x in BANNED):
                    continue

                ticker = exchange.fetch_ticker(sym)
                volume = safe(ticker.get('quoteVolume'))
                percentage = abs(safe(ticker.get('percentage')))

                # Hacim ve volatilite filtresi
                if volume < MIN_VOLUME:
                    continue

                if percentage < MIN_VOLATILITY:
                    continue

                candles = exchange.fetch_ohlcv(sym,'5m',limit=30)
                closes = [c[4] for c in candles]

                ema9 = sum(closes[-9:])/9
                ema21 = sum(closes[-21:])/21

                # Pump başlangıcı long
                if ema9 > ema21 and closes[-1] > max(closes[-5:-1]):
                    if open_trade(sym,"long"):
                        break

                # Dump başlangıcı short
                if ema9 < ema21 and closes[-1] < min(closes[-5:-1]):
                    if open_trade(sym,"short"):
                        break

                time.sleep(0.2)

            time.sleep(10)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(10)

@bot.message_handler(func=lambda m: True)
def stop(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID):
        return
    if msg.text.lower()=="dur":
        os._exit(0)

if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🚀 SMART SCALP ENGINE AKTİF")
    bot.infinity_polling()
