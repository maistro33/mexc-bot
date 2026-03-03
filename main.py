import os
import time
import ccxt
import telebot
import threading
from datetime import datetime, timezone

# ===== SETTINGS =====
LEV = 10
FIXED_MARGIN = 2.0
MAX_DAILY_STOPS = 3
MIN_VOLUME = 20_000_000
TOP_COINS = 80
SPREAD_LIMIT = 0.0015

TP1_ROE = 10
TP2_ROE = 22
TRAIL_CANDLES = 8
BUFFER = 0.002  # %0.2 güvenlik payı

# ===== TELEGRAM =====
bot = telebot.TeleBot(os.getenv("TELE_TOKEN"), threaded=True)
bot.remove_webhook()
CHAT_ID = os.getenv("MY_CHAT_ID")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": "Berfin33",
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
})

trade_state = {}
daily_stops = 0
last_day = datetime.now(timezone.utc).day


# ===== HELPERS =====
def safe(x):
    try:
        return float(x)
    except:
        return 0.0


def has_position():
    try:
        pos = exchange.fetch_positions()
        return any(safe(p.get("contracts")) > 0 for p in pos)
    except:
        return False


def get_symbols():
    try:
        tickers = exchange.fetch_tickers()
        pairs = []

        for sym, data in tickers.items():
            if ":USDT" not in sym:
                continue

            if safe(data.get("quoteVolume")) >= MIN_VOLUME:
                pairs.append((sym, safe(data.get("quoteVolume"))))

        pairs.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in pairs[:TOP_COINS]]
    except:
        return []


def ema(values, length):
    if len(values) < length:
        return None
    return sum(values[-length:]) / length


def get_direction(sym):
    try:
        h4 = exchange.fetch_ohlcv(sym, "4h", limit=60)
        h1 = exchange.fetch_ohlcv(sym, "1h", limit=30)

        h4_close = [c[4] for c in h4]
        h1_close = [c[4] for c in h1]

        ema50 = ema(h4_close, 50)
        ema20 = ema(h1_close, 20)

        if ema50 is None or ema20 is None:
            return None

        if h4_close[-1] > ema50 and h1_close[-1] > ema20:
            return "long"

        if h4_close[-1] < ema50 and h1_close[-1] < ema20:
            return "short"

        return None

    except:
        return None


def entry_signal(sym, direction):
    try:
        m15 = exchange.fetch_ohlcv(sym, "15m", limit=20)
        highs = [c[2] for c in m15]
        lows = [c[3] for c in m15]
        closes = [c[4] for c in m15]

        if direction == "long":
            breakout = closes[-2] > max(highs[-7:-2])
            pullback = closes[-1] < closes[-2]
            return breakout and pullback

        if direction == "short":
            breakout = closes[-2] < min(lows[-7:-2])
            pullback = closes[-1] > closes[-2]
            return breakout and pullback

        return False

    except:
        return False


# ===== POSITION MANAGER =====
def manage():
    global daily_stops, last_day

    while True:
        try:
            if datetime.now(timezone.utc).day != last_day:
                daily_stops = 0
                last_day = datetime.now(timezone.utc).day

            positions = exchange.fetch_positions()

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                entry = safe(p["entryPrice"])
                direction = "long" if p["side"] == "long" else "short"
                price = safe(exchange.fetch_ticker(sym)["last"])

                roe = ((price - entry) / entry) * LEV * 100
                if direction == "short":
                    roe = ((entry - price) / entry) * LEV * 100

                if sym not in trade_state:
                    trade_state[sym] = {"tp1": False, "tp2": False}

                # ===== STRUCTURAL SL =====
                candles = exchange.fetch_ohlcv(sym, "15m", limit=12)
                highs = [c[2] for c in candles]
                lows = [c[3] for c in candles]

                if direction == "long":
                    structural_sl = min(lows[:-1]) * (1 - BUFFER)
                    if price <= structural_sl:
                        exchange.create_market_order(
                            sym, "sell", qty, params={"reduceOnly": True}
                        )
                        daily_stops += 1
                        trade_state.pop(sym, None)
                        bot.send_message(CHAT_ID, f"❌ STRUCTURAL SL {sym}")
                        continue

                if direction == "short":
                    structural_sl = max(highs[:-1]) * (1 + BUFFER)
                    if price >= structural_sl:
                        exchange.create_market_order(
                            sym, "buy", qty, params={"reduceOnly": True}
                        )
                        daily_stops += 1
                        trade_state.pop(sym, None)
                        bot.send_message(CHAT_ID, f"❌ STRUCTURAL SL {sym}")
                        continue

                # ===== TP1 =====
                if roe >= TP1_ROE and not trade_state[sym]["tp1"]:
                    part = qty * 0.4
                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        part,
                        params={"reduceOnly": True}
                    )
                    trade_state[sym]["tp1"] = True
                    bot.send_message(CHAT_ID, f"💰 TP1 {sym}")

                # ===== TP2 =====
                if roe >= TP2_ROE and not trade_state[sym]["tp2"]:
                    part = qty * 0.3
                    exchange.create_market_order(
                        sym,
                        "sell" if direction == "long" else "buy",
                        part,
                        params={"reduceOnly": True}
                    )
                    trade_state[sym]["tp2"] = True
                    bot.send_message(CHAT_ID, f"🚀 TP2 {sym}")

                # ===== TRAILING (mum bazlı) =====
                if trade_state[sym]["tp2"]:
                    trail_candles = exchange.fetch_ohlcv(sym, "15m", limit=TRAIL_CANDLES + 1)
                    highs_t = [c[2] for c in trail_candles]
                    lows_t = [c[3] for c in trail_candles]

                    if direction == "long":
                        trail_sl = min(lows_t[:-1])
                        if price <= trail_sl:
                            exchange.create_market_order(
                                sym, "sell", qty, params={"reduceOnly": True}
                            )
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🏁 TRAIL EXIT {sym}")

                    if direction == "short":
                        trail_sl = max(highs_t[:-1])
                        if price >= trail_sl:
                            exchange.create_market_order(
                                sym, "buy", qty, params={"reduceOnly": True}
                            )
                            trade_state.pop(sym, None)
                            bot.send_message(CHAT_ID, f"🏁 TRAIL EXIT {sym}")

            time.sleep(5)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(5)


# ===== ENTRY LOOP =====
def run():
    global daily_stops

    while True:
        try:
            if daily_stops >= MAX_DAILY_STOPS:
                time.sleep(60)
                continue

            if has_position():
                time.sleep(15)
                continue

            for sym in get_symbols():

                ticker = exchange.fetch_ticker(sym)
                spread = (ticker["ask"] - ticker["bid"]) / ticker["last"]
                if spread > SPREAD_LIMIT:
                    continue

                direction = get_direction(sym)
                if not direction:
                    continue

                if not entry_signal(sym, direction):
                    continue

                notional = FIXED_MARGIN * LEV
                qty = notional / ticker["last"]

                market = exchange.market(sym)
                precision = market.get("precision", {}).get("amount", 0)

                try:
                    precision = int(precision)
                except:
                    precision = 0

                if precision == 0:
                    qty = int(qty)
                else:
                    qty = round(qty, precision)

                if qty <= 0:
                    continue

                exchange.set_leverage(LEV, sym)

                exchange.create_market_order(
                    sym,
                    "buy" if direction == "long" else "sell",
                    qty
                )

                trade_state[sym] = {"tp1": False, "tp2": False}

                bot.send_message(CHAT_ID, f"📈 {sym} {direction.upper()} OPEN")
                break

            time.sleep(20)

        except Exception as e:
            print("RUN ERROR:", e)
            time.sleep(20)


# ===== START =====
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=run, daemon=True).start()

bot.send_message(CHAT_ID, "🔥 PRO HYBRID BOT AKTİF")
bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
