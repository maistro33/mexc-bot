import os, time, telebot, ccxt, threading

TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TELE_TOKEN)

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

def safe(x):
    try: return float(x)
    except: return 0.0

# ===== AYAR =====
MARGIN = 2
LEV = 10
MAX_POS = 4
SL = 0.45

TRAIL_START = 0.6   # erken kapatmaz
profits = {}

BANNED = ['BTC','ETH','XRP','SOL']

# ===== BTC TREND =====
def btc_trend():
    try:
        ex = get_exch()
        candles = ex.fetch_ohlcv('BTC/USDT:USDT','5m',limit=4)
        return candles[-1][4] - candles[0][4]  # pozitif: yükseliyor
    except:
        return 0

# ===== EMİR =====
def open_trade(sym, side):
    try:
        ex = get_exch()

        # BTC yön filtresi
        trend = btc_trend()
        if side == "long" and trend < 0:
            return
        if side == "short" and trend > 0:
            return

        pos = ex.fetch_positions()
        active = [p for p in pos if safe(p.get('contracts'))>0]

        if len(active) >= MAX_POS:
            return
        if any(p['symbol']==sym for p in active):
            return

        price = safe(ex.fetch_ticker(sym)['last'])

        # TAM 2 USDT MARGIN
        qty = (MARGIN * LEV) / price
        qty = float(ex.amount_to_precision(sym, qty))

        ex.set_leverage(LEV, sym)

        ex.create_market_order(
            sym,
            "buy" if side=="long" else "sell",
            qty
        )

        profits[sym] = 0
        bot.send_message(MY_CHAT_ID,f"🔥 {sym} {side.upper()}")

    except as e:
        print(e)

# ===== KAR YÖNETİMİ =====
def manager():
    while True:
        try:
            ex = get_exch()

            for p in [p for p in ex.fetch_positions() if safe(p.get('contracts'))>0]:

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
                    ex.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty, params={'reduceOnly':True})
                    profits.pop(sym,None)

                # AKILLI TRAILING
                elif profits[sym] >= TRAIL_START:

                    # kâr büyüdükçe takip genişler
                    gap = profits[sym] * 0.35

                    if profits[sym] - profit >= gap:
                        ex.create_market_order(sym,
                            'sell' if side=='long' else 'buy',
                            qty, params={'reduceOnly':True})
                        profits.pop(sym,None)

            time.sleep(2)
        except:
            time.sleep(2)

# ===== SCANNER =====
def scanner():
    while True:
        try:
            ex = get_exch()
            markets = ex.load_markets()

            pos = ex.fetch_positions()
            active = [p for p in pos if safe(p.get('contracts'))>0]

            for m in markets.values():

                sym = m['symbol']
                if ':USDT' not in sym: continue
                if any(x in sym for x in BANNED): continue
                if len(active) >= MAX_POS: break

                candles = ex.fetch_ohlcv(sym,'5m',limit=20)
                closes = [c[4] for c in candles]
                vols = [c[5] for c in candles]

                ema9 = sum(closes[-9:])/9
                ema20 = sum(closes)/20
                vol_spike = vols[-1] > sum(vols[:-1])/len(vols[:-1])

                # LONG
                if ema9 > ema20 and vol_spike \
                   and closes[-1] > ema9:
                    open_trade(sym,"long")

                # SHORT
                if ema9 < ema20 and vol_spike \
                   and closes[-1] < ema9:
                    open_trade(sym,"short")

            time.sleep(3)
        except:
            time.sleep(3)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def stop(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID): return
    if msg.text.lower()=="dur":
        os._exit(0)

# ===== BAŞLAT =====
if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"💀 ULTIMATE BOT AKTİF")
    bot.infinity_polling()
