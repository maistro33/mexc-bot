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

# ===== SABİT AYAR =====
MARGIN = 3            # SABİT 3 USDT
LEV = 10
MAX_POS = 1           # TEK POZİSYON

FIXED_STOP = 0.45     # Max zarar ~0.45 USDT

# SCALP TRAILING
BE_TRIGGER = 0.40     # +0.40'da break-even
LOCK_TRIGGER = 0.70   # +0.70'de min kâr kilitle
TIGHT_TRIGGER = 1.00  # +1.00'de sıkı takip

BANNED = ['BTC','ETH','XRP','SOL']

exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

profits = {}
lock = threading.Lock()

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

# ===== POZİSYON AÇ =====
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
            "buy" if side == "long" else "sell",
            qty
        )

        with lock:
            profits[sym] = 0

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

                # ----- HARD STOP -----
                if profit <= -FIXED_STOP:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)
                    continue

                # ----- BREAK EVEN -----
                if peak >= BE_TRIGGER and profit <= 0:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)
                    continue

                # ----- LOCK PROFIT -----
                if peak >= LOCK_TRIGGER and profit <= 0.30:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)
                    continue

                # ----- TIGHT TRAILING -----
                if peak >= TIGHT_TRIGGER and peak - profit >= 0.30:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)

            time.sleep(2)

        except Exception as e:
            print("MANAGER:", e)
            time.sleep(2)

# ===== SCANNER =====
def scanner():
    markets = exchange.load_markets()

    while True:
        try:
            positions = [p for p in exchange.fetch_positions()
                         if safe(p.get('contracts')) > 0]

            if len(positions) >= MAX_POS:
                time.sleep(5)
                continue

            for m in markets.values():
                sym = m['symbol']

                if ':USDT' not in sym:
                    continue
                if any(x in sym for x in BANNED):
                    continue

                candles = exchange.fetch_ohlcv(sym, '5m', limit=30)
                closes = [c[4] for c in candles]

                ema9 = sum(closes[-9:])/9
                ema21 = sum(closes[-21:])/21

                # LONG
                if ema9 > ema21 and closes[-1] > closes[-2]:
                    if open_trade(sym, "long"):
                        break

                # SHORT
                if ema9 < ema21 and closes[-1] < closes[-2]:
                    if open_trade(sym, "short"):
                        break

            time.sleep(6)

        except Exception as e:
            print("SCAN:", e)
            time.sleep(6)

# ===== TELEGRAM STOP =====
@bot.message_handler(func=lambda m: True)
def stop(msg):
    if str(msg.chat.id) != str(MY_CHAT_ID):
        return
    if msg.text.lower() == "dur":
        os._exit(0)

# ===== START =====
if __name__ == "__main__":
    threading.Thread(target=manager, daemon=True).start()
    threading.Thread(target=scanner, daemon=True).start()
    bot.send_message(MY_CHAT_ID, "⚡ STABLE SCALP MODE AKTİF")
    bot.infinity_polling()
