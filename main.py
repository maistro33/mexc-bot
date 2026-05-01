import ccxt, time, os, telebot, threading
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = int(os.getenv("MY_CHAT_ID"))

bot = telebot.TeleBot(TOKEN)

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

MARGIN = 3
LEVERAGE = 10

bot_position = None
manual_positions = []
signal_cache = {}
last_signal_time = 0
last_close_time = 0
lock = False

# ==============================
def get_data(sym):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, "1m", limit=50)
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
        df["ema"] = df["c"].ewm(span=20).mean()
        return df
    except:
        return None

# ==============================
def analyze(df):
    price = df["c"].iloc[-1]
    ema = df["ema"].iloc[-1]

    prev = df["c"].iloc[-2]
    prev2 = df["c"].iloc[-3]

    change = abs(price - df["c"].iloc[-5]) / df["c"].iloc[-5]

    if change < 0.002:
        return None, 0, "Zayıf hareket"

    if abs(price - df["c"].iloc[-3]) < 0.001:
        return None, 0, "Zayıf momentum"

    if price > ema and prev < ema and prev2 < ema:
        return "LONG", 95, "EMA kırılım + teyit"

    if price < ema and prev > ema and prev2 > ema:
        return "SHORT", 95, "EMA kırılım + teyit"

    return None, 0, "Trend yok"

# ==============================
def get_real_size(sym):
    try:
        positions = exchange.fetch_positions()
        for p in positions:
            if p["symbol"].replace("/","").replace(":USDT","") == sym.replace("/","").replace(":USDT",""):
                return float(p.get("contracts", 0))
    except:
        pass
    return 0

# ==============================
def scanner():
    global last_signal_time, bot_position, last_close_time

    while True:
        try:
            if time.time() - last_close_time < 15:
                time.sleep(3)
                continue

            tickers = exchange.fetch_tickers()

            for sym, data in tickers.items():

                if time.time() - last_signal_time < 10:
                    continue

                if ":USDT" not in sym:
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                if df["v"].iloc[-1] < 80:
                    continue

                safe = sym.replace("/","").replace(":","")

                # 🔥 CACHE FIX
                if safe in signal_cache and time.time() - signal_cache[safe]["t"] < 60:
                    continue

                sig, score, reason = analyze(df)
                if sig is None:
                    continue

                price = df["c"].iloc[-1]

                signal_cache[safe] = {
                    "sym": sym,
                    "price": price,
                    "signal": sig,
                    "t": time.time()
                }

                decision = "🔥 GİR" if not bot_position else "❌ PAS"

                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("✅ GİR", callback_data=f"enter|{safe}"))

                bot.send_message(
                    CHAT_ID,
                    f"""💀 AKILLI SİNYAL

📊 {sym}
📈 {sig}
💰 {round(price,4)}

🎯 TP: +0.70 USDT
🛑 SL: -0.50 USDT

🤖 Güç: %{score}
🤖 Karar: {decision}
📊 Sebep: {reason}
""",
                    reply_markup=markup
                )

                last_signal_time = time.time()

                if score >= 90 and not bot_position:
                    open_trade(signal_cache[safe], False)

                time.sleep(1)

            time.sleep(8)

        except Exception as e:
            print("SCAN ERROR:", e)
            time.sleep(5)

# ==============================
def open_trade(data, is_manual):
    global bot_position, manual_positions, lock

    if lock:
        return

    if not is_manual and bot_position:
        return

    lock = True

    try:
        side = "buy" if data["signal"]=="LONG" else "sell"
        price = data["price"]

        exchange.set_leverage(LEVERAGE, data["sym"])

        amount = (MARGIN * LEVERAGE) / price

        exchange.create_market_order(data["sym"], side, float(amount))

        pos = {
            "sym": data["sym"],
            "type": data["signal"],
            "entry": price,
            "max": 0,
            "trailing": False,
            "open_time": time.time()
        }

        if is_manual:
            manual_positions.append(pos)
            bot.send_message(CHAT_ID, f"🧑 MANUEL AÇILDI {data['sym']}")
        else:
            bot_position = pos
            bot.send_message(CHAT_ID, f"🤖 BOT AÇTI {data['sym']}")

    except Exception as e:
        print("OPEN ERROR:", e)

    lock = False

# ==============================
def close_trade(pos, reason, is_manual):
    global bot_position, manual_positions, last_close_time

    try:
        side = "sell" if pos["type"]=="LONG" else "buy"
        size = get_real_size(pos["sym"])

        if size > 0:
            exchange.create_market_order(pos["sym"], side, size)

        bot.send_message(CHAT_ID, f"⛔ {pos['sym']} {reason}")

    except Exception as e:
        print("CLOSE ERROR:", e)

    if is_manual:
        if pos in manual_positions:
            manual_positions.remove(pos)
    else:
        bot_position = None
        last_close_time = time.time()

# ==============================
def manage():
    global bot_position, manual_positions

    while True:
        try:
            all_positions = []

            if bot_position:
                all_positions.append((bot_position, False))

            for p in manual_positions:
                all_positions.append((p, True))

            for pos, is_manual in all_positions:

                if time.time() - pos["open_time"] < 5:
                    continue

                price = exchange.fetch_ticker(pos["sym"])["last"]

                if pos["type"] == "LONG":
                    pnl = (price - pos["entry"]) / pos["entry"] * (MARGIN * LEVERAGE)
                else:
                    pnl = (pos["entry"] - price) / pos["entry"] * (MARGIN * LEVERAGE)

                if pnl > pos["max"]:
                    pos["max"] = pnl

                if pnl >= 0.60 and not pos["trailing"]:
                    pos["trailing"] = True

                if pos["trailing"]:
                    if pnl < pos["max"] - 0.25:
                        close_trade(pos, "TRAIL", is_manual)

                if pnl <= -0.50:
                    close_trade(pos, "SL", is_manual)

        except Exception as e:
            print("MANAGE ERROR:", e)

        time.sleep(2)

# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data.startswith("enter|"):
        data = signal_cache.get(call.data.split("|")[1])
        if data:
            open_trade(data, True)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()

bot.send_message(CHAT_ID, "💀 BOT AKTİF (FINAL FIX)")
bot.infinity_polling()
