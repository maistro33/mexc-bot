import os
import time
import ccxt
import telebot
import threading
import requests
from datetime import datetime, timezone, timedelta

# ================= SETTINGS =================

LEV = 10
MARGIN = 2

MAX_DAILY_TRADES = 6
MAX_POSITIONS = 4

TP1_PCT = 0.008
TP2_PCT = 0.016
TRAIL_GAP = 0.012

TP1_RATIO = 0.30
TP2_RATIO = 0.40

COOLDOWN_MIN = 60

MIN_VOLUME = 5000000
MAX_SPREAD = 0.003

WHALE_CHECK_INTERVAL = 300

# ================= COINS =================

SYMBOLS = [
"INJ/USDT:USDT","SEI/USDT:USDT","SUI/USDT:USDT","APT/USDT:USDT",
"TIA/USDT:USDT","PYTH/USDT:USDT","AVAX/USDT:USDT","DOT/USDT:USDT",
"ATOM/USDT:USDT","NEAR/USDT:USDT","ARB/USDT:USDT","OP/USDT:USDT",
"IMX/USDT:USDT","RENDER/USDT:USDT","FET/USDT:USDT","GRT/USDT:USDT",
"GALA/USDT:USDT","ALGO/USDT:USDT","KAS/USDT:USDT","JASMY/USDT:USDT",
"PEPE/USDT:USDT","FLOKI/USDT:USDT","BOME/USDT:USDT","WIF/USDT:USDT"
]

whale_symbols = set()
last_whale_check = 0

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

markets = exchange.load_markets()

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

def get_qty(sym):
    try:
        pos = exchange.fetch_positions([sym])
        if not pos:
            return 0
        return safe(pos[0]["contracts"])
    except:
        return 0

# ================= SYNC EXISTING POSITIONS =================

def sync_existing_positions():

    try:

        positions = exchange.fetch_positions()

        for p in positions:

            qty = safe(p.get("contracts"))

            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p["entryPrice"])
            side = "long" if p["side"] == "long" else "short"

            trade_state[sym] = {
            "entry": entry,
            "direction": side,
            "tp1": False,
            "tp2": False,
            "extreme": entry
            }

        print("Synced existing positions")

    except Exception as e:

        print("SYNC ERROR:",e)

# ================= WHALE DETECT =================

def detect_whale_coin():

    try:

        url="https://open-api.coinglass.com/api/pro/v1/futures/openInterest/ohlc"

        headers={
        "accept":"application/json",
        "coinglassSecret":os.getenv("COINGLASS_API")
        }

        r=requests.get(url,headers=headers,timeout=10).json()

        data=r.get("data",[])

        if not data:
            return None

        coin=data[0]["symbol"]

        return f"{coin}/USDT:USDT"

    except Exception as e:

        print("WHALE ERROR:",e)
        return None

# ================= ENTRY =================

def open_trade(sym,direction):

    global daily_trades

    try:

        if get_qty(sym) > 0:
            return

        ticker = exchange.fetch_ticker(sym)

        if ticker["quoteVolume"] < MIN_VOLUME:
            return

        spread=(ticker["ask"]-ticker["bid"])/ticker["last"]

        if spread > MAX_SPREAD:
            return

        price = ticker["last"]

        qty=(MARGIN*LEV)/price
        qty=float(exchange.amount_to_precision(sym,qty))

        exchange.set_leverage(LEV,sym)

        side="buy" if direction=="long" else "sell"

        exchange.create_market_order(sym,side,qty)

        trade_state[sym]={"entry":price,"direction":direction,"tp1":False,"tp2":False,"extreme":price}

        cooldown[sym]=datetime.now()+timedelta(minutes=COOLDOWN_MIN)

        daily_trades+=1

        bot.send_message(CHAT_ID,f"🚀 {sym} {direction}")

    except Exception as e:

        print("ENTRY ERROR:",e)

# ================= MANAGE =================

def manage():

    while True:

        try:

            pos=exchange.fetch_positions()

            for p in pos:

                qty=safe(p.get("contracts"))

                if qty<=0:
                    continue

                sym=p["symbol"]

                if sym not in trade_state:
                    continue

                state=trade_state[sym]

                price=exchange.fetch_ticker(sym)["last"]

                entry=state["entry"]
                direction=state["direction"]

                side="sell" if direction=="long" else "buy"

                if direction=="long" and price>state["extreme"]:
                    state["extreme"]=price

                if direction=="short" and price<state["extreme"]:
                    state["extreme"]=price

                if not state["tp1"]:

                    if (direction=="long" and price>=entry*(1+TP1_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP1_PCT)):

                        exchange.create_market_order(sym,side,qty*TP1_RATIO,params={"reduceOnly":True})

                        state["tp1"]=True

                        bot.send_message(CHAT_ID,f"💰 TP1 {sym}")

                if not state["tp2"]:

                    if (direction=="long" and price>=entry*(1+TP2_PCT)) or \
                       (direction=="short" and price<=entry*(1-TP2_PCT)):

                        exchange.create_market_order(sym,side,qty*TP2_RATIO,params={"reduceOnly":True})

                        state["tp2"]=True

                        bot.send_message(CHAT_ID,f"💰 TP2 {sym}")

                elif state["tp2"]:

                    if direction=="long":

                        if price<=state["extreme"]*(1-TRAIL_GAP):

                            exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})
                            trade_state.pop(sym)

                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

                    else:

                        if price>=state["extreme"]*(1+TRAIL_GAP):

                            exchange.create_market_order(sym,side,qty,params={"reduceOnly":True})
                            trade_state.pop(sym)

                            bot.send_message(CHAT_ID,f"🏁 TRAILING {sym}")

            time.sleep(3)

        except Exception as e:

            print("MANAGE ERROR:",e)
            time.sleep(5)

# ================= START =================

print("BOT STARTING")

sync_existing_positions()

threading.Thread(target=manage,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
