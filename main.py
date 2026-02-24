import os
import time
import telebot
import ccxt
import threading

# ===== TELEGRAM & API =====
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TELE_TOKEN)

# ===== SETTINGS =====
MARGIN = 3
LEV = 10
MAX_POS = 1

FIXED_STOP = 0.40        # Maksimum zarar
TRAIL_START = 0.60       # 0.60 USDT kara gelince takip başlar
TRAIL_GAP = 0.30         # 0.30 geri çekilirse kapatır

BANNED = ['BTC','ETH','XRP','SOL','BNB']

profits = {}
lock = threading.Lock()

# ===== EXCHANGE =====
exchange = ccxt.bitget({
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

# ===== INDICATORS =====
def ema(data, period):
    k = 2/(period+1)
    val = data[0]
    for p in data[1:]:
        val = p*k + val*(1-k)
    return val

def adx(candles, period=14):
    ups,downs,tr=[],[],[]
    for i in range(1,len(candles)):
        high,low,prev_high,prev_low = candles[i][2],candles[i][3],candles[i-1][2],candles[i-1][3]
        up=high-prev_high
        down=prev_low-low
        ups.append(max(up,0) if up>down else 0)
        downs.append(max(down,0) if down>up else 0)
        tr.append(max(high-low,abs(high-candles[i-1][4]),abs(low-candles[i-1][4])))
    atr_val=sum(tr[-period:])
    if atr_val==0:return 0
    plus=100*(sum(ups[-period:])/atr_val)
    minus=100*(sum(downs[-period:])/atr_val)
    dx=100*abs(plus-minus)/(plus+minus) if (plus+minus)!=0 else 0
    return dx

# ===== POSITION SIZE =====
def calculate_size(sym):
    price = safe(exchange.fetch_ticker(sym)['last'])
    notional = MARGIN * LEV
    qty = notional / price
    return float(exchange.amount_to_precision(sym, qty))

# ===== OPEN TRADE =====
def open_trade(sym, side):
    try:
        exchange.set_leverage(LEV, sym)
        qty = calculate_size(sym)
        if qty <= 0:
            return False

        exchange.create_market_order(
            sym,
            "buy" if side=="long" else "sell",
            qty
        )

        with lock:
            profits[sym] = 0

        bot.send_message(MY_CHAT_ID,f"🎯 {sym} {side.upper()} (3 USDT)")
        return True

    except Exception as e:
        print("OPEN:",e)
        return False

# ===== MANAGER =====
def manager():
    while True:
        try:
            positions = [p for p in exchange.fetch_positions()
                         if safe(p.get('contracts'))>0]

            for p in positions:
                sym=p['symbol']
                side=p['side']
                qty=safe(p.get('contracts'))
                entry=safe(p.get('entryPrice'))
                last=safe(exchange.fetch_ticker(sym)['last'])

                profit=(last-entry)*qty if side=="long" else (entry-last)*qty

                with lock:
                    if profit>profits.get(sym,0):
                        profits[sym]=profit
                    peak=profits.get(sym,0)

                # SABİT STOP
                if profit <= -FIXED_STOP:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)
                    continue

                # TRAILING
                if peak >= TRAIL_START and peak - profit >= TRAIL_GAP:
                    exchange.create_market_order(
                        sym,
                        'sell' if side=='long' else 'buy',
                        qty,
                        params={'reduceOnly':True}
                    )
                    profits.pop(sym,None)

            time.sleep(2)

        except Exception as e:
            print("MANAGER:",e)
            time.sleep(2)

# ===== SCANNER =====
def scanner():
    markets = exchange.load_markets()

    while True:
        try:
            positions=[p for p in exchange.fetch_positions()
                       if safe(p.get('contracts'))>0]

            if len(positions)>=MAX_POS:
                time.sleep(5)
                continue

            best_setup=None
            best_score=0

            for m in markets.values():
                sym=m['symbol']

                if ':USDT' not in sym:
                    continue
                if any(x in sym for x in BANNED):
                    continue

                candles=exchange.fetch_ohlcv(sym,'5m',limit=40)
                closes=[c[4] for c in candles]

                ema9=ema(closes[-30:],9)
                ema21=ema(closes[-30:],21)
                strength=adx(candles)

                momentum_up=closes[-1]>closes[-2]>closes[-3]
                momentum_down=closes[-1]<closes[-2]<closes[-3]

                score=strength

                if ema9>ema21 and momentum_up and strength>18:
                    if score>best_score:
                        best_score=score
                        best_setup=(sym,"long")

                if ema9<ema21 and momentum_down and strength>18:
                    if score>best_score:
                        best_score=score
                        best_setup=(sym,"short")

            if best_setup:
                sym,side=best_setup
                if open_trade(sym,side):
                    time.sleep(10)

            time.sleep(6)

        except Exception as e:
            print("SCAN:",e)
            time.sleep(6)

# ===== TELEGRAM STOP =====
@bot.message_handler(func=lambda m: True)
def stop(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID):
        return
    if msg.text.lower()=="dur":
        os._exit(0)

# ===== START =====
if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🛡️ FIXED STOP 0.40 MODE AKTİF")
    bot.infinity_polling()
