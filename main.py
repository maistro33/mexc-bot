import os
import time
import telebot
import ccxt
import threading
import datetime

# ===== TELEGRAM & API =====
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')

PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TELE_TOKEN)

# ===== CORE SETTINGS =====
RISK_PCT = 0.008
LEV = 10
MAX_POS = 1

DAILY_LOSS_LIMIT = 0.05
GLOBAL_DD_LIMIT = 0.15

ATR_MULT = 2.0
TRAIL_STAGE1 = 1.5
TRAIL_STAGE2 = 1.0
TRAIL_STAGE3 = 0.6

BANNED = ['BTC','ETH','XRP','SOL','BNB']

profits = {}
lock = threading.Lock()

start_balance = None
peak_balance = None
today = datetime.date.today()

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

# ===== UTILS =====
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

def atr(candles, period=14):
    trs=[]
    for i in range(1,len(candles)):
        h,l,pc = candles[i][2], candles[i][3], candles[i-1][4]
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs[-period:])/period

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

# ===== RISK CONTROL =====
def check_risk():
    global start_balance, peak_balance, today

    balance = exchange.fetch_balance()['USDT']['total']

    if start_balance is None:
        start_balance = balance
        peak_balance = balance

    if datetime.date.today() != today:
        today = datetime.date.today()
        start_balance = balance

    if balance > peak_balance:
        peak_balance = balance

    if balance < start_balance*(1-DAILY_LOSS_LIMIT):
        bot.send_message(MY_CHAT_ID,"🛑 Daily loss limit hit.")
        os._exit(0)

    if balance < peak_balance*(1-GLOBAL_DD_LIMIT):
        bot.send_message(MY_CHAT_ID,"💀 Max drawdown reached.")
        os._exit(0)

# ===== POSITION SIZE =====
def calculate_size(sym):
    balance = exchange.fetch_balance()['USDT']['free']
    risk_amount = balance * RISK_PCT

    candles = exchange.fetch_ohlcv(sym,'5m',limit=50)
    a = atr(candles)
    stop_dist = a * ATR_MULT

    if stop_dist == 0:
        return 0, a

    qty = risk_amount / stop_dist
    return float(exchange.amount_to_precision(sym, qty)), a

# ===== OPEN TRADE =====
def open_trade(sym, side):
    try:
        check_risk()

        exchange.set_leverage(LEV, sym)

        qty, _ = calculate_size(sym)
        if qty <= 0:
            return False

        exchange.create_market_order(
            sym,
            "buy" if side=="long" else "sell",
            qty
        )

        with lock:
            profits[sym]=0

        bot.send_message(MY_CHAT_ID,f"🎯 {sym} {side.upper()}")
        return True

    except Exception as e:
        print("OPEN:",e)
        return False

# ===== MANAGER =====
def manager():
    while True:
        try:
            check_risk()

            positions = [p for p in exchange.fetch_positions()
                         if safe(p.get('contracts'))>0]

            for p in positions:
                sym=p['symbol']
                side=p['side']
                qty=safe(p.get('contracts'))
                entry=safe(p.get('entryPrice'))
                last=safe(exchange.fetch_ticker(sym)['last'])

                candles=exchange.fetch_ohlcv(sym,'5m',limit=50)
                a=atr(candles)

                profit=(last-entry)*qty if side=="long" else (entry-last)*qty

                with lock:
                    if profit>profits.get(sym,0):
                        profits[sym]=profit
                    peak=profits.get(sym,0)

                # ATR Stop
                if profit<=-(a*ATR_MULT):
                    exchange.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,params={'reduceOnly':True})
                    profits.pop(sym,None)
                    continue

                # Trailing Stages
                if peak>a*4 and peak-profit>=a*TRAIL_STAGE1:
                    exchange.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,params={'reduceOnly':True})
                    profits.pop(sym,None)
                    continue

                if peak>a*7 and peak-profit>=a*TRAIL_STAGE2:
                    exchange.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,params={'reduceOnly':True})
                    profits.pop(sym,None)
                    continue

                if peak>a*10 and peak-profit>=a*TRAIL_STAGE3:
                    exchange.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,params={'reduceOnly':True})
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

            # açık pozisyon varsa yeni açma
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

                candles=exchange.fetch_ohlcv(sym,'5m',limit=50)
                closes=[c[4] for c in candles]

                ema9=ema(closes[-30:],9)
                ema21=ema(closes[-30:],21)
                trend_strength=adx(candles)

                momentum_up=closes[-1]>closes[-2]>closes[-3]
                momentum_down=closes[-1]<closes[-2]<closes[-3]

                score=trend_strength

                if ema9>ema21 and momentum_up and trend_strength>18:
                    if score>best_score:
                        best_score=score
                        best_setup=(sym,"long")

                if ema9<ema21 and momentum_down and trend_strength>18:
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
    bot.send_message(MY_CHAT_ID,"🧠 STABLE SCALP ENGINE AKTİF")
    bot.infinity_polling()
