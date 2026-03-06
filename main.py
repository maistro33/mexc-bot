import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone, timedelta

# ================= SETTINGS =================

LEV = 10
MARGIN = 4

MAX_DAILY_TRADES = 6
MAX_POSITIONS = 2

TP1_PCT = 0.008
TP2_PCT = 0.016
TRAIL_GAP = 0.012

TP1_RATIO = 0.30
TP2_RATIO = 0.40

COOLDOWN_MIN = 60

MIN_VOLUME = 5_000_000
MAX_SPREAD = 0.003

# ================= COINS =================

SYMBOLS = [

"INJ/USDT:USDT","SEI/USDT:USDT","SUI/USDT:USDT","APT/USDT:USDT",
"TIA/USDT:USDT","PYTH/USDT:USDT",

"AVAX/USDT:USDT","DOT/USDT:USDT","ATOM/USDT:USDT","NEAR/USDT:USDT",
"ARB/USDT:USDT","OP/USDT:USDT","IMX/USDT:USDT","RENDER/USDT:USDT",

"FET/USDT:USDT","GRT/USDT:USDT","GALA/USDT:USDT","ALGO/USDT:USDT",

"KAS/USDT:USDT","JASMY/USDT:USDT",

"PEPE/USDT:USDT","FLOKI/USDT:USDT","BOME/USDT:USDT","WIF/USDT:USDT"

]

# ================= TELEGRAM =================

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

# ================= EXCHANGE =================

exchange = ccxt.bitget({
"apiKey": os.getenv("BITGET_API"),
"secret": os.getenv("BITGET_SEC"),
"password": "Berfin33",
"options": {"defaultType": "swap"},
"enableRateLimit": True
})

# ================= STATE =================

trade_state = {}
cooldown = {}

daily_trades = 0
current_day = datetime.now(timezone.utc).day

# ================= HELPERS =================

def safe(x):
    try:
        return float(x)
    except:
        return 0

def reset_daily():

    global daily_trades,current_day

    now_day = datetime.now(timezone.utc).day

    if now_day != current_day:

        daily_trades = 0
        current_day = now_day

def has_position():

    try:

        positions = exchange.fetch_positions()

        active = 0

        for p in positions:

            if safe(p.get("contracts")) > 0:

                active += 1

        return active >= MAX_POSITIONS

    except:

        return False

def get_qty(sym):

    try:

        pos = exchange.fetch_positions([sym])

        if not pos:
            return 0

        return safe(pos[0]["contracts"])

    except:

        return 0

# ================= TREND =================

def trend_direction(sym):

    try:

        h4 = exchange.fetch_ohlcv(sym,"4h",limit=60)

        closes=[c[4] for c in h4]

        ema=sum(closes[-50:])/50

        if closes[-1] > ema:
            return "long"

        if closes[-1] < ema:
            return "short"

    except:
        return None

# ================= RETEST =================

def retest(sym,direction):

    try:

        h1=exchange.fetch_ohlcv(sym,"1h",limit=20)

        highs=[c[2] for c in h1]
        lows=[c[3] for c in h1]

        if direction=="long":
            return lows[-1] <= min(lows[-5:-1])
        else:
            return highs[-1] >= max(highs[-5:-1])

    except:
        return False

# ================= BREAKOUT =================

def breakout(sym):

    try:

        m15=exchange.fetch_ohlcv(sym,"15m",limit=15)

        highs=[c[2] for c in m15]
        lows=[c[3] for c in m15]
        closes=[c[4] for c in m15]

        last = m15[-1]
        prev = m15[-2]

        # pump filtresi
        move = abs(last[4]-prev[4]) / prev[4]

        if move > 0.025:
            return None

        resistance=max(highs[:-1])
        support=min(lows[:-1])

        last_close=closes[-1]

        # fake breakout filtresi
        body=abs(last[4]-last[1])
        candle_range=last[2]-last[3]

        if candle_range == 0:
            return None

        if body/candle_range < 0.5:
            return None

        if last_close > resistance:
            return "long"

        if last_close < support:
            return "short"

    except:
        return None

# ================= VOLATILITY =================

def volatility(sym):

    try:

        m15=exchange.fetch_ohlcv(sym,"15m",limit=10)

        last=m15[-1]
        prev=m15[-2]

        body=abs(last[4]-last[1])
        avg=sum(abs(c[4]-c[1]) for c in m15[:-1])/9

        if body > avg*1.8:

            if last[4] > prev[4]:
                return "long"

            if last[4] < prev[4]:
                return "short"

    except:
        return None

# ================= ENTRY =================

def open_trade(sym,direction):

    global daily_trades

    try:

        ticker=exchange.fetch_ticker(sym)

        # volume filtresi
        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        # spread filtresi
        spread=(ticker["ask"]-ticker["bid"])/ticker["last"]

        if spread > MAX_SPREAD:
            return

        price=ticker["last"]

        qty=(MARGIN*LEV)/price
        qty=float(exchange.amount_to_precision(sym,qty))

        exchange.set_leverage(LEV,sym)

        side="buy" if direction=="long" else "sell"

        exchange.create_market_order(sym,side,qty)

        trade_state[sym] = {

        "entry":price,
        "direction":direction,
        "tp1":False,
        "tp2":False,
        "extreme":price

        }

        cooldown[sym] = datetime.now() + timedelta(minutes=COOLDOWN_MIN)

        daily_trades+=1

        bot.send_message(CHAT_ID,f"🚀 {sym} {direction}")

    except Exception as e:

        print("ENTRY ERROR",e)

# ================= MANAGE =================

def manage():

    while True:

        try:

            if not trade_state:
                time.sleep(8)
                continue

            pos=exchange.fetch_positions()

            for p in pos:

                qty=safe(p.get("contracts"))

                if qty <=0:
                    continue

                sym=p["symbol"]

                if sym not in trade_state:
                    continue

                state=trade_state[sym]

                price=exchange.fetch_ticker(sym)["last"]

                entry=state["entry"]
                direction=state["direction"]

                side="sell" if direction=="long" else "buy"

                if direction=="long" and price > state["extreme"]:
                    state["extreme"]=price

                if direction=="short" and price < state["extreme"]:
                    state["extreme"]=price

                if not state["tp1"]:

                    if (direction=="long" and price>=entry*(1+TP1_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP1_PCT)):

                        exchange.create_market_order(sym,side,qty*TP1_RATIO,params={"reduceOnly":True})

                        state["tp1"]=True

                        bot.send_message(CHAT_ID,f"💰 TP1 {sym}")

                elif not state["tp2"]:

                    if (direction=="long" and price>=entry*(1+TP2_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP2_PCT)):

                        exchange.create_market_order(sym,side,qty*TP2_RATIO,params={"reduceOnly":True})

                        state["tp2"]=True

                        bot.send_message(CHAT_ID,f"💰 TP2 {sym}")

                elif state["tp2"]:

                    if direction=="long":

                        if price <= state["extreme"]*(1-TRAIL_GAP):

                            exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})

                            trade_state.pop(sym)

                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

                    else:

                        if price >= state["extreme"]*(1+TRAIL_GAP):

                            exchange.create_market_order(sym,side,get_qty(sym),params={"reduceOnly":True})

                            trade_state.pop(sym)

                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

            time.sleep(10)

        except:
            time.sleep(10)

# ================= RUN =================

def run():

    global daily_trades

    while True:

        try:

            reset_daily()

            if daily_trades >= MAX_DAILY_TRADES:
                time.sleep(60)
                continue

            if has_position():
                time.sleep(12)
                continue

            for sym in SYMBOLS:

                if sym in cooldown and datetime.now() < cooldown[sym]:
                    continue

                direction=trend_direction(sym)

                if direction and retest(sym,direction):

                    open_trade(sym,direction)
                    break

                b=breakout(sym)

                if b:
                    open_trade(sym,b)
                    break

                v=volatility(sym)

                if v:
                    open_trade(sym,v)
                    break

            time.sleep(45)

        except:

            time.sleep(45)

# ================= START =================

print("BOT STARTING")

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=run,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
