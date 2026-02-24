import os, time, ccxt, telebot, threading
from datetime import datetime, timedelta

# ================= API =================
TELE_TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("MY_CHAT_ID")
API_KEY = os.getenv("BITGET_API")
API_SEC = os.getenv("BITGET_SEC")
PASSPHRASE = os.getenv("BITGET_PASS")

bot = telebot.TeleBot(TELE_TOKEN)

def exchange():
    return ccxt.bitget({
        "apiKey": API_KEY,
        "secret": API_SEC,
        "password": PASSPHRASE,
        "options": {"defaultType": "swap"},
        "enableRateLimit": True
    })

# ================= AYAR =================
MARGIN = 5
LEV = 10
MAX_POS = 1
DAILY_MAX_LOSS = 2
SL = 0.6
TRAIL_START = 1.0
FEE_BUFFER = 0.08

BLACKLIST = ["BTC","ETH","SOL","BNB","XRP"]

profits = {}
daily_loss = 0
today = datetime.now().date()

# ================= EMA =================
def ema(data, period):
    if len(data) < period:
        return sum(data)/len(data)
    return sum(data[-period:]) / period

# ================= BTC TREND =================
def btc_mode():
    try:
        ex = exchange()
        candles = ex.fetch_ohlcv("BTC/USDT","1h",limit=50)
        closes = [c[4] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]

        ema20 = ema(closes,20)
        ema50 = ema(closes,50)

        trend = "none"
        if ema20 > ema50:
            trend = "long"
        elif ema20 < ema50:
            trend = "short"

        # ADX benzeri basit trend gücü ölçümü
        ranges = [highs[i]-lows[i] for i in range(-15,-1)]
        avg_range = sum(ranges)/len(ranges)

        if avg_range < closes[-1]*0.003:
            return "none"

        return trend
    except:
        return "none"

# ================= OPEN TRADE =================
def open_trade(symbol, side):
    global daily_loss, today

    if daily_loss >= DAILY_MAX_LOSS:
        return

    try:
        ex = exchange()

        price = ex.fetch_ticker(symbol)["last"]
        qty = (MARGIN * LEV) / price
        qty = float(ex.amount_to_precision(symbol, qty))

        ex.set_leverage(LEV, symbol)

        ex.create_market_order(
            symbol,
            "buy" if side=="long" else "sell",
            qty
        )

        profits[symbol] = 0
        bot.send_message(CHAT_ID,f"🚀 {symbol} {side.upper()} açıldı")

    except Exception as e:
        print("OPEN ERROR:", e)

# ================= MANAGER =================
def manager():
    global daily_loss, today

    while True:
        try:
            ex = exchange()
            positions = [p for p in ex.fetch_positions() if float(p["contracts"])>0]

            for p in positions:
                sym = p["symbol"].split(":")[0]
                side = p["side"]
                qty = float(p["contracts"])
                entry = float(p["entryPrice"])
                last = ex.fetch_ticker(sym)["last"]

                profit = (last-entry)*qty if side=="long" else (entry-last)*qty
                profit -= FEE_BUFFER

                if profit > profits.get(sym,0):
                    profits[sym] = profit

                # STOP
                if profit <= -SL:
                    ex.create_market_order(
                        sym,
                        "sell" if side=="long" else "buy",
                        qty,
                        params={"reduceOnly":True}
                    )
                    daily_loss += abs(profit)
                    profits.pop(sym,None)

                # TRAILING
                elif profits[sym] >= TRAIL_START:
                    peak = profits[sym]
                    gap = peak*0.25 if peak < 2 else peak*0.15

                    if peak - profit >= gap:
                        ex.create_market_order(
                            sym,
                            "sell" if side=="long" else "buy",
                            qty,
                            params={"reduceOnly":True}
                        )
                        profits.pop(sym,None)

            time.sleep(3)
        except Exception as e:
            print("MANAGER ERROR:", e)
            time.sleep(3)

# ================= SCANNER =================
def scanner():
    while True:
        try:
            ex = exchange()

            if len([p for p in ex.fetch_positions() if float(p["contracts"])>0]) >= MAX_POS:
                time.sleep(5)
                continue

            mode = btc_mode()
            if mode == "none":
                time.sleep(10)
                continue

            markets = ex.load_markets()

            for m in markets.values():
                symbol = m["symbol"]

                if ":USDT" not in symbol:
                    continue

                if any(x in symbol for x in BLACKLIST):
                    continue

                ticker = ex.fetch_ticker(symbol)
                if ticker["quoteVolume"] < 5_000_000:
                    continue

                candles = ex.fetch_ohlcv(symbol,"5m",limit=40)
                closes = [c[4] for c in candles]
                highs = [c[2] for c in candles]
                lows = [c[3] for c in candles]
                vols = [c[5] for c in candles]

                breakout_up = closes[-1] > max(highs[-20:-1])
                breakout_down = closes[-1] < min(lows[-20:-1])

                vol_spike = vols[-1] > (sum(vols[:-1])/len(vols[:-1]))*1.8

                if mode=="long" and breakout_up and vol_spike:
                    open_trade(symbol,"long")
                    break

                if mode=="short" and breakout_down and vol_spike:
                    open_trade(symbol,"short")
                    break

            time.sleep(5)

        except Exception as e:
            print("SCANNER ERROR:", e)
            time.sleep(5)

# ================= START =================
if __name__=="__main__":
    threading.Thread(target=manager,daemon=True).start()
    threading.Thread(target=scanner,daemon=True).start()
    bot.send_message(CHAT_ID,"🔥 ADAPTİF BOT AKTİF")
    bot.infinity_polling()
