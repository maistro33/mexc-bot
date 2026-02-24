import os, time, telebot, ccxt, threading, datetime, math

TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASS')

bot = telebot.TeleBot(TELE_TOKEN)

# ===== CORE SETTINGS (DOKUNMA) =====
RISK_PCT = 0.008
LEV = 10
MAX_POS = 1
DAILY_LOSS_LIMIT = 0.05
GLOBAL_DD_LIMIT = 0.15

ATR_MULT = 2.2
TRAIL_STAGE1 = 1.8
TRAIL_STAGE2 = 1.2
TRAIL_STAGE3 = 0.8

profits = {}
lock = threading.Lock()

start_balance = None
peak_balance = None
today = datetime.date.today()

BANNED = ['BTC','ETH','XRP','SOL']

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
    try: return float(x)
    except: return 0.0

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
def check_risk(ex):
    global start_balance, peak_balance, today

    balance = ex.fetch_balance()['USDT']['total']

    if start_balance is None:
        start_balance = balance
        peak_balance = balance

    if datetime.date.today() != today:
        today = datetime.date.today()
        start_balance = balance

    if balance > peak_balance:
        peak_balance = balance

    # daily stop
    if balance < start_balance*(1-DAILY_LOSS_LIMIT):
        bot.send_message(MY_CHAT_ID,"🛑 Daily loss limit hit.")
        os._exit(0)

    # global DD stop
    if balance < peak_balance*(1-GLOBAL_DD_LIMIT):
        bot.send_message(MY_CHAT_ID,"💀 Max drawdown reached.")
        os._exit(0)

# ===== POSITION SIZE =====
def calculate_size(ex, sym):
    balance = ex.fetch_balance()['USDT']['free']
    risk_amount = balance * RISK_PCT

    candles = ex.fetch_ohlcv(sym,'5m',limit=50)
    a = atr(candles)
    stop_dist = a * ATR_MULT

    qty = risk_amount / stop_dist
    return float(ex.amount_to_precision(sym, qty)), a

# ===== OPEN TRADE =====
def open_trade(sym, side):
    try:
        ex = get_exch()
        check_risk(ex)

        ex.set_leverage(LEV, sym)

        qty, a = calculate_size(ex, sym)
        if qty <= 0: return

        ex.create_market_order(sym,
            "buy" if side=="long" else "sell",
            qty)

        with lock:
            profits[sym]=0

        bot.send_message(MY_CHAT_ID,f"🎯 {sym} {side.upper()}")

    except Exception as e:
        print("OPEN:",e)

# ===== MANAGER =====
def manager():
    while True:
        try:
            ex=get_exch()
            check_risk(ex)

            for p in [p for p in ex.fetch_positions() if safe(p.get('contracts'))>0]:

                sym=p['symbol']
                side=p['side']
                qty=safe(p.get('contracts'))
                entry=safe(p.get('entryPrice'))
                last=safe(ex.fetch_ticker(sym)['last'])

                candles=ex.fetch_ohlcv(sym,'5m',limit=50)
                a=atr(candles)

                profit=(last-entry)*qty if side=="long" else (entry-last)*qty

                with lock:
                    if profit>profits.get(sym,0):
                        profits[sym]=profit
                    peak=profits.get(sym,0)

                # HARD STOP
                if profit<=-(a*ATR_MULT):
                    ex.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,params={'reduceOnly':True})
                    profits.pop(sym,None)
                    continue

                # TRAILING ENGINE
                if peak>a*4 and peak-profit>=a*TRAIL_STAGE1:
                    ex.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,params={'reduceOnly':True})
                    profits.pop(sym,None)
                    continue

                if peak>a*7 and peak-profit>=a*TRAIL_STAGE2:
                    ex.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,params={'reduceOnly':True})
                    profits.pop(sym,None)
                    continue

                if peak>a*10 and peak-profit>=a*TRAIL_STAGE3:
                    ex.create_market_order(sym,
                        'sell' if side=='long' else 'buy',
                        qty,params={'reduceOnly':True})
                    profits.pop(sym,None)

            time.sleep(2)
        except Exception as e:
            print("MANAGER:",e)
            time.sleep(2)

# ===== SCANNER =====
def scanner():
    ex=get_exch()
    markets=ex.load_markets()

    while True:
        try:
            positions=[p for p in ex.fetch_positions() if safe(p.get('contracts'))>0]
            if len(positions)>=MAX_POS:
                time.sleep(5)
                continue

            for m in markets.values():
                sym=m['symbol']
                if ':USDT' not in sym: continue
                if any(x in sym for x in BANNED): continue

                # 1H trend
                c1h=ex.fetch_ohlcv(sym,'1h',limit=100)
                close1h=[c[4] for c in c1h]
                ema200_1h=ema(close1h[-200:],200)

                # 15m structure
                c15=ex.fetch_ohlcv(sym,'15m',limit=50)
                close15=[c[4] for c in c15]
                ema50_15=ema(close15[-50:],50)

                # 5m entry
                c5=ex.fetch_ohlcv(sym,'5m',limit=50)
                close5=[c[4] for c in c5]
                ema9=ema(close5[-30:],9)
                ema21=ema(close5[-30:],21)
                trend_strength=adx(c5)

                funding=safe(ex.fetch_funding_rate(sym)['fundingRate'])

                # LONG
                if (close1h[-1]>ema200_1h and
                    close15[-1]>ema50_15 and
                    ema9>ema21 and
                    trend_strength>18 and
                    funding<0.015):
                    open_trade(sym,"long")

                # SHORT
                if (close1h[-1]<ema200_1h and
                    close15[-1]<ema50_15 and
                    ema9<ema21 and
                    trend_strength>18 and
                    funding>-0.015):
                    open_trade(sym,"short")

            time.sleep(7)
        except Exception as e:
            print("SCAN:",e)
            time.sleep(7)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def stop(msg):
    if str(msg.chat.id)!=str(MY_CHAT_ID): return
    if msg.text.lower()=="dur":
        os._exit(0)

# ===== START =====
if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(MY_CHAT_ID,"🧠 INSTITUTIONAL ENGINE AKTİF")
    bot.infinity_polling()
