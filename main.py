import os
import time
import telebot
import ccxt
import threading
import datetime

# ===== TELEGRAM =====
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TELE_TOKEN)

# ===== AYAR =====
LEV = 10
MAX_POS = 2
RISK_PERCENT = 0.25
FIXED_STOP = 0.45
DAILY_MAX_LOSS = -1.5

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
last_trade_time = {}
daily_pnl = 0
today = datetime.date.today()
lock = threading.Lock()

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

def get_margin_size(sym):
    balance = exchange.fetch_balance()['USDT']['free']
    margin = balance * RISK_PERCENT
    price = safe(exchange.fetch_ticker(sym)['last'])
    qty = (margin * LEV) / price
    return float(exchange.amount_to_precision(sym, qty))

# ===== OPEN =====
def open_trade(sym, side):
    global daily_pnl
    try:
        if daily_pnl <= DAILY_MAX_LOSS:
            return False

        positions = [p for p in exchange.fetch_positions()
                     if safe(p.get('contracts')) > 0]

        if len(positions) >= MAX_POS:
            return False

        # aynı coine 5 dk içinde tekrar girme
        if sym in last_trade_time:
            if time.time() - last_trade_time[sym] < 300:
                return False

        exchange.set_leverage(LEV, sym)
        qty = get_margin_size(sym)

        exchange.create_market_order(
            sym,
            "buy" if side=="long" else "sell",
            qty
        )

        with lock:
            profits[sym] = 0
            lock_levels[sym] = 0
            last_trade_time[sym] = time.time()

        bot.send_message(MY_CHAT_ID, f"🎯 {sym} {side.upper()}")
        return True

    except Exception as e:
        print("OPEN ERROR:", e)
        return False

# ===== MANAGER =====
def manager():
    global daily_pnl, today

    while True:
        try:
            # gün reset
            if datetime.date.today() != today:
                today = datetime.date.today()
                daily_pnl = 0

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

                # HARD STOP
                if profit <= -FIXED_STOP:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    daily_pnl += profit
                    profits.pop(sym,None)
                    lock_levels.pop(sym,None)
                    continue

                # LOCK 0.50 BE
                if peak >= 0.50 and locked < 0:
                    lock_levels[sym] = 0

                # LOCK 0.80 → 0.50
                if peak >= 0.80 and locked < 0.50:
                    lock_levels[sym] = 0.50

                # LOCK 1.20 → 0.90
                if peak >= 1.20 and locked < 0.90:
                    lock_levels[sym] = 0.90

                # TRAILING 1.80+
                if peak >= 1.80:
                    lock_levels[sym] = max(lock_levels.get(sym,0), peak - 0.40)

                locked = lock_levels.get(sym, 0)

                if locked > 0 and profit <= locked:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    daily_pnl += profit
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
    bot.send_message(MY_CHAT_ID,"⚡ AKTİF DÖNGÜ SCALP vFINAL AKTİF")
    bot.infinity_polling()
