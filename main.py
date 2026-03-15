import os
import time
import ccxt
import telebot
import threading
import requests

LEV = 10
MARGIN = 3

MAX_POSITIONS = 3
BALINA_LIMIT = 1

TP1_PCT = 0.006
TP2_PCT = 0.009
TRAIL_GAP = 0.008

TP1_RATIO = 0.50
TP2_RATIO = 0.25

MIN_VOLUME = 5000000
MAX_SPREAD = 0.003
SCAN_DELAY = 6

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
CHAT_ID = os.getenv("MY_CHAT_ID")

exchange = ccxt.bitget({
"apiKey": os.getenv("BITGET_API"),
"secret": os.getenv("BITGET_SEC"),
"password": "Berfin33",
"options": {"defaultType": "swap"},
"enableRateLimit": True
})

markets = exchange.load_markets()

SYMBOLS = [s for s in markets if markets[s]["swap"] and "USDT" in s][:120]

trade_state = {}

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


def rsi_filter(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=15)
        closes=[c[4] for c in candles]

        gains=[]
        losses=[]

        for i in range(1,len(closes)):
            diff=closes[i]-closes[i-1]

            if diff>0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(diff))

        avg_gain=sum(gains)/14
        avg_loss=sum(losses)/14

        if avg_loss==0:
            return 100

        rs=avg_gain/avg_loss
        rsi=100-(100/(1+rs))

        return rsi
    except:
        return 50


def btc_panic():
    try:
        candles=exchange.fetch_ohlcv("BTC/USDT:USDT","5m",limit=2)
        change=(candles[-1][4]-candles[-2][4])/candles[-2][4]

        if change < -0.015:
            return True

        return False
    except:
        return False


def volatility_filter(sym):
    try:
        candles=exchange.fetch_ohlcv(sym,"5m",limit=10)
        ranges=[c[2]-c[3] for c in candles]
        avg=sum(ranges[:-1])/9

        if ranges[-1] > avg*3:
            return True

        return False
    except:
        return False


# 🔧 DÜZELTİLMİŞ restart senkronizasyonu
def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:

            qty = safe(p.get("contracts"))

            if qty <= 0:
                continue

            sym = p["symbol"]
            entry = safe(p["entryPrice"])
            side = "long" if p["side"] == "long" else "short"

            initial_size = (MARGIN * LEV) / entry

            tp1_done = False

            if qty < initial_size * 0.75:
                tp1_done = True

            trade_state[sym] = {
                "entry": entry,
                "direction": side,
                "tp1": tp1_done,
                "tp2": False,
                "be": tp1_done,
                "extreme": entry,
                "start": time.time()
            }

    except:
        pass


def btc_trend():
    try:
        candles = exchange.fetch_ohlcv("BTC/USDT:USDT","1h",limit=50)
        closes=[c[4] for c in candles]
        ema=sum(closes[-20:])/20

        if closes[-1] > ema:
            return "bull"

        return "bear"

    except:
        return "neutral"


def orderbook_pressure(sym):

    try:

        ob=exchange.fetch_order_book(sym,limit=20)

        bid=sum([b[1] for b in ob["bids"]])
        ask=sum([a[1] for a in ob["asks"]])

        if bid > ask*1.5:
            return "long"

        if ask > bid*1.5:
            return "short"

        return None

    except:
        return None


def volume_spike(sym):

    try:

        candles=exchange.fetch_ohlcv(sym,"5m",limit=6)

        vols=[c[5] for c in candles]

        avg=sum(vols[:-1])/5

        if vols[-1] > avg*1.5:
            return True

        return False

    except:
        return False


def funding_flip(sym):

    try:

        fr=exchange.fetch_funding_rate(sym)

        rate=fr["fundingRate"]

        if abs(rate) > 0.0005:
            return True

        return False

    except:
        return False


def liquidation_heatmap(sym):

    try:

        candles=exchange.fetch_ohlcv(sym,"1m",limit=10)

        ranges=[c[2]-c[3] for c in candles]

        avg=sum(ranges[:-1])/9

        if ranges[-1] > avg*2:
            return True

        return False

    except:
        return False


def fake_breakout(sym):

    try:

        candles=exchange.fetch_ohlcv(sym,"5m",limit=5)

        highs=[c[2] for c in candles]
        lows=[c[3] for c in candles]

        last=candles[-1]

        if last[4] < highs[-2] and last[2] > highs[-2]:
            return True

        if last[4] > lows[-2] and last[3] < lows[-2]:
            return True

        return False

    except:
        return False


def liquidity_sweep(sym):

    try:

        candles=exchange.fetch_ohlcv(sym,"15m",limit=10)

        highs=[c[2] for c in candles]
        lows=[c[3] for c in candles]

        if highs[-1] > max(highs[:-1]) or lows[-1] < min(lows[:-1]):
            return True

        return False

    except:
        return False


def short_squeeze(sym):

    try:

        candles = exchange.fetch_ohlcv(sym,"5m",limit=3)

        change=(candles[-1][4]-candles[-2][4])/candles[-2][4]

        if change > 0.02 and volume_spike(sym):
            return True

        return False

    except:
        return False


def long_squeeze(sym):

    try:

        candles = exchange.fetch_ohlcv(sym,"5m",limit=3)

        change=(candles[-2][4]-candles[-1][4])/candles[-2][4]

        if change > 0.02 and volume_spike(sym):
            return True

        return False

    except:
        return False


def liquidation_hunt(sym):

    try:

        candles = exchange.fetch_ohlcv(sym,"1m",limit=6)

        ranges=[c[2]-c[3] for c in candles]

        avg=sum(ranges[:-1])/5

        if ranges[-1] > avg*2.5:
            return True

        return False

    except:
        return False


def early_pump(sym):

    try:

        candles = exchange.fetch_ohlcv(sym,"5m",limit=4)

        high=max([c[2] for c in candles[:-1]])

        if candles[-1][4] > high and volume_spike(sym):
            return True

        return False

    except:
        return False


def coinglass_whale():

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

        return coin

    except:
        return None


def whale_signal(sym):

    try:

        coin=coinglass_whale()

        if not coin:
            return None

        if coin not in sym:
            return None

        if not volume_spike(sym):
            return None

        if not funding_flip(sym):
            return None

        if not liquidation_heatmap(sym):
            return None

        return True

    except:
        return None


# geri kalan manage(), scanner() ve bot başlatma kısmı
# senin gönderdiğin kod ile birebir aynıdır

print("BOT STARTING")

sync_positions()

threading.Thread(target=manage,daemon=True).start()
threading.Thread(target=scanner,daemon=True).start()

bot.send_message(CHAT_ID,"🤖 BOT AKTİF")

bot.infinity_polling()
