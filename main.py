import os
import time
import ccxt
import telebot
import threading
import websocket
import json
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

# ================= WHALE =================

WHALE_THRESHOLD = 120000
WHALE_DELAY = 1.2
WHALE_SYMBOL = "BTCUSDT"

last_whale_side = None
last_whale_time = 0

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


def orderbook_imbalance(sym):

    try:

        ob = exchange.fetch_order_book(sym, limit=20)

        bids = ob["bids"]
        asks = ob["asks"]

        bid_vol = sum([b[1] for b in bids])
        ask_vol = sum([a[1] for a in asks])

        if bid_vol > ask_vol * 1.8:
            return "long"

        if ask_vol > bid_vol * 1.8:
            return "short"

        return None

    except:
        return None


def volume_spike(sym):

    try:

        m5 = exchange.fetch_ohlcv(sym,"5m",limit=6)

        vols=[c[5] for c in m5]

        if vols[-1] > (sum(vols[:-1])/5)*2:
            return True

        return False

    except:
        return False


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

        resistance=max(highs[:-1])
        support=min(lows[:-1])

        last_close=m15[-1][4]

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

        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        spread=(ticker["ask"]-ticker["bid"])/ticker["last"]

        if spread > MAX_SPREAD:
            return

        price=ticker["last"]

        qty=(MARGIN*LEV)/price
        qty=float(exchange.amount_to_precision(sym,qty))

        exchange.set_leverage(LEV,sym)

        side="buy" if direction=="long" else "sell"

        exchange.create_market_order(sym,side,qty)

        bot.send_message(CHAT_ID,f"🚀 {sym} {direction}")

    except Exception as e:

        print("ENTRY ERROR",e)

# ================= WHALE COPY =================

def whale_action(side,sym):

    global last_whale_side

    try:

        if not has_position():

            direction = "long" if side=="buy" else "short"

            if orderbook_imbalance(sym) != direction:
                return

            if not volume_spike(sym):
                return

            time.sleep(WHALE_DELAY)

            open_trade(sym,direction)

            last_whale_side = side

            bot.send_message(CHAT_ID,f"🐋 Whale {sym} {direction}")

    except Exception as e:

        print("WHALE ERROR",e)

# ================= WHALE STREAM =================

def whale_stream():

    global last_whale_time

    url="wss://ws.bitget.com/v2/ws/public"

    def on_message(ws,message):

        global last_whale_time

        try:

            data=json.loads(message)

            if "data" not in data:
                return

            for trade in data["data"]:

                symbol = trade["instId"]

                price=float(trade["price"])
                size=float(trade["size"])

                value=price*size

                if value > WHALE_THRESHOLD:

                    if time.time() - last_whale_time < 5:
                        return

                    last_whale_time = time.time()

                    side=trade["side"]

                    coin = symbol.replace("USDT","")

                    sym = coin + "/USDT:USDT"

                    whale_action(side,sym)

        except:
            pass


    def on_open(ws):

        sub={
        "op":"subscribe",
        "args":[
            {"instType":"SPOT","channel":"trade","instId":WHALE_SYMBOL}
        ]
        }

        ws.send(json.dumps(sub))


    while True:

        try:

            ws=websocket.WebSocketApp(
                url,
                on_message=on_message,
                on_open=on_open
            )

            ws.run_forever()

        except:

            time.sleep(5)

# ================= START =================

print("BOT STARTING")

threading.Thread(target=whale_stream,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
