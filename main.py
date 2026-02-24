import os
import time
import telebot
import ccxt
import threading

# ===== ENV =====
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')

bot = telebot.TeleBot(TELE_TOKEN)

# ===== EXCHANGE =====
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

# ===== AYAR (STABİL) =====
MARGIN = 3
LEV = 10
MAX_POS = 1

SL = 0.6
TRAIL_START = 1.0
TRAIL_GAP = 0.3

profits = {}

BANNED = ['BTC','ETH','XRP','SOL','BNB','DOGE']

# ===== BTC TREND FİLTRE =====
def btc_trend():
    try:
        ex = get_exch()
        candles = ex.fetch_ohlcv('BTC/USDT:USDT','15m',limit=20)
        closes = [c[4] for c in candles]
        ema20 = sum(closes)/20
        return closes[-1] > ema20
    except Exception as e:
        print("BTC ERROR:", e)
        return False

# ===== EMİR AÇ =====
def open_trade(sym, side):
    try:
        ex = get_exch()

        positions = ex.fetch_positions()
        active = [p for p in positions if safe(p.get('contracts')) > 0]

        if len(active) >= MAX_POS:
            return

        if any(p['symbol'] == sym for p in active):
            return

        ticker = ex.fetch_ticker(sym)
        price = safe(ticker['last'])

        qty = (MARGIN * LEV) / price
        qty = float(ex.amount_to_precision(sym, qty))

        ex.set_leverage(LEV, sym)

        ex.create_market_order(
            sym,
            "buy" if side == "long" else "sell",
            qty
        )

        profits[sym] = 0
        bot.send_message(MY_CHAT_ID, f"🔥 {sym} {side.upper()} açıldı")

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== KAR YÖNETİMİ =====
def manager():
    while True:
        try:
            ex = get_exch()
            positions = ex.fetch_positions()

            for p in positions:
                if safe(p.get('contracts')) <= 0:
                    continue

                sym = p['symbol']
                side = p['side']
                qty = safe(p.get('contracts'))
                entry = safe(p.get('entryPrice'))
                last = safe(ex.fetch_ticker(sym)['last'])

                profit = (last-entry)*qty if side=="long" else (entry-last)*qty

                if profit > profits.get(sym,0):
                    profits[sym] = profit

                # STOP LOSS
                if profit <= -SL:
                    ex.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)

                # TRAILING
                elif profits.get(sym,0) >= TRAIL_START and \
                     profits[sym] - profit >= TRAIL_GAP:
                    ex.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)

            time.sleep(2)

        except Exception as e:
            print("MANAGER ERROR:", e)
            time.sleep(2)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            ex = get_exch()
            markets = ex.load_markets()

            btc_up = btc_trend()

            positions = ex.fetch_positions()
            active = [p for p in positions if safe(p.get('contracts')) > 0]

            for m in markets.values():

                sym = m['symbol']

                if ':USDT' not in sym:
                    continue

                if any(x in sym for x in BANNED):
                    continue

                if len(active) >= MAX_POS:
                    break

                ticker = ex.fetch_ticker(sym)

                # HACİM FİLTRESİ (minimum 5M)
                if safe(ticker.get('quoteVolume')) < 5_000_000:
                    continue

                candles = ex.fetch_ohlcv(sym,'5m',limit=30)

                closes = [c[4] for c in candles]
                highs = [c[2] for c in candles]
                lows = [c[3] for c in candles]
                vols = [c[5] for c in candles]

                ema9 = sum(closes[-9:])/9
                ema20 = sum(closes[-20:])/20

                vol_spike = vols[-1] > sum(vols[-10:-1])/9

                breakout_up = closes[-1] > max(highs[-10:-1])
                breakout_down = closes[-1] < min(lows[-10:-1])

                # LONG
                if btc_up and ema9 > ema20 and vol_spike and breakout_up:
                    open_trade(sym,"long")

                # SHORT
                if not btc_up and ema9 < ema20 and vol_spike and breakout_down:
                    open_trade(sym,"short")

            time.sleep(4)

        except Exception as e:
            print("SCANNER ERROR:", e)
            time.sleep(4)

# ===== TELEGRAM STOP =====
@bot.message_handler(func=lambda m: True)
def stop_bot(msg):
    if str(msg.chat.id) != str(MY_CHAT_ID):
        return

    if msg.text.lower() == "dur":
        os._exit(0)

# ===== BAŞLAT =====
if __name__ == "__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🔥 STABİL BREAKOUT BOT AKTİF")
    bot.infinity_polling()
