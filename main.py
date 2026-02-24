import os, time, telebot, ccxt, threading
from datetime import datetime, timedelta

# ===== API =====
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

# ===== AYAR (25 USDT) =====
MARGIN = 2
LEV = 10
MAX_POS = 2
SL = 0.32
TRAIL_START = 0.65
FEE_BUFFER = 0.05

BANNED = ['BTC','ETH','SOL','XRP']
profits = {}
consecutive_sl = 0
cooldown_until = None

# ===== BASİT EMA =====
def ema(data, period):
    if len(data) < period:
        return sum(data)/len(data)
    return sum(data[-period:]) / period

# ===== BTC TREND 15m =====
def btc_trend():
    try:
        ex = get_exch()
        candles = ex.fetch_ohlcv('BTC/USDT','15m',limit=30)
        closes = [c[4] for c in candles]
        ema9 = ema(closes,9)
        ema21 = ema(closes,21)
        if ema9 > ema21:
            return "long"
        elif ema9 < ema21:
            return "short"
        else:
            return "none"
    except:
        return "none"

# ===== OPEN TRADE =====
def open_trade(sym, side):
    global cooldown_until

    if cooldown_until and datetime.now() < cooldown_until:
        return

    try:
        ex = get_exch()

        trend = btc_trend()
        if trend != side:
            return

        positions = ex.fetch_positions()
        active = [p for p in positions if safe(p.get('contracts')) > 0]

        if len(active) >= MAX_POS:
            return

        if any(p['symbol']==sym for p in active):
            return

        price = safe(ex.fetch_ticker(sym)['last'])
        qty = (MARGIN * LEV) / price
        qty = float(ex.amount_to_precision(sym, qty))

        try:
            ex.set_leverage(LEV, sym)
        except:
            pass

        ex.create_market_order(
            sym,
            "buy" if side=="long" else "sell",
            qty
        )

        profits[sym] = 0
        bot.send_message(MY_CHAT_ID,f"🚀 {sym} {side.upper()} açıldı")

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== MANAGER =====
def manager():
    global consecutive_sl, cooldown_until

    while True:
        try:
            ex = get_exch()
            positions = [p for p in ex.fetch_positions() if safe(p.get('contracts'))>0]

            for p in positions:
                sym = p['symbol']
                side = p['side']
                qty = safe(p.get('contracts'))
                entry = safe(p.get('entryPrice'))
                last = safe(ex.fetch_ticker(sym)['last'])

                profit = (last-entry)*qty if side=="long" else (entry-last)*qty
                profit -= FEE_BUFFER

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
                    consecutive_sl += 1

                    if consecutive_sl >= 3:
                        cooldown_until = datetime.now() + timedelta(minutes=30)
                        bot.send_message(MY_CHAT_ID,"⛔ 3 SL — 30 dk duruyor")

                # TRAILING
                elif profits[sym] >= TRAIL_START:
                    peak = profits[sym]

                    if peak < 1:
                        gap = peak * 0.30
                    elif peak < 2:
                        gap = peak * 0.20
                    else:
                        gap = peak * 0.15

                    if peak - profit >= gap:
                        ex.create_market_order(
                            sym,
                            'sell' if side=='long' else 'buy',
                            qty,
                            params={'reduceOnly':True}
                        )
                        profits.pop(sym,None)
                        consecutive_sl = 0

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
            trend = btc_trend()

            for m in markets.values():
                sym = m['symbol']

                if ':USDT' not in sym:
                    continue

                if any(x in sym for x in BANNED):
                    continue

                candles = ex.fetch_ohlcv(sym,'5m',limit=30)
                closes = [c[4] for c in candles]
                highs = [c[2] for c in candles]
                lows = [c[3] for c in candles]
                vols = [c[5] for c in candles]

                avg_range = sum([highs[i]-lows[i] for i in range(-15,-1)]) / 14
                last_range = highs[-1] - lows[-1]
                avg_vol = sum(vols[:-1]) / len(vols[:-1])

                breakout_up = closes[-1] > max(highs[-20:-1])
                breakout_down = closes[-1] < min(lows[-20:-1])
                vol_spike = vols[-1] > avg_vol * 2
                overextended = last_range > avg_range * 2.5

                if vol_spike and not overextended:

                    if breakout_up and trend=="long":
                        open_trade(sym,"long")

                    if breakout_down and trend=="short":
                        open_trade(sym,"short")

            time.sleep(4)

        except Exception as e:
            print("SCANNER ERROR:", e)
            time.sleep(4)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def stop(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID):
        return

    if msg.text.lower()=="dur":
        bot.send_message(MY_CHAT_ID,"⏸️ Bot durduruldu")
        os._exit(0)

# ===== START =====
if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🔥 FINAL BOT AKTİF")
    bot.infinity_polling()
