import ccxt, time, os, telebot, threading
import pandas as pd
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==============================
TOKEN = os.getenv("TELE_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = telebot.TeleBot(TOKEN)

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

bot_position = None
manual_positions = []
signal_cache = {}
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

    move = price - df["c"].iloc[-5]
    vol = df["v"].iloc[-1] / df["v"].iloc[-5]

    score = 0

    if price > ema:
        signal = "LONG"
        score += 40
    else:
        signal = "SHORT"
        score += 40

    if abs(move) > 0:
        score += 30

    if vol > 1.2:
        score += 30

    return signal, score

# ==============================
def scanner():
    global bot_position, last_close_time

    while True:
        try:
            if bot_position:
                time.sleep(5)
                continue

            if time.time() - last_close_time < 40:
                time.sleep(5)
                continue

            tickers = exchange.fetch_tickers()

            for sym in tickers:

                if ":USDT" not in sym:
                    continue

                if any(x in sym for x in ["BTC","ETH","XRP"]):
                    continue

                vol = tickers[sym]["quoteVolume"]
                if vol < 1000000:
                    continue

                df = get_data(sym)
                if df is None:
                    continue

                sig, score = analyze(df)

                if score < 70:
                    continue

                safe = sym.replace("/","").replace(":","")

                if safe in signal_cache:
                    continue

                price = df["c"].iloc[-1]

                signal_cache[safe] = {
                    "sym": sym,
                    "price": price,
                    "signal": sig
                }

                decision = "🔥 GİR" if score >= 90 else "❌ PAS"

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
📊 Sebep: Trend + Momentum + Volume
""",
                    reply_markup=markup
                )

                # AUTO TRADE
                if score >= 90 and not bot_position:
                    open_trade(signal_cache[safe], False)

                time.sleep(2)

            time.sleep(15)

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
        amount = 30 / price

        exchange.create_market_order(data["sym"], side, amount)

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

        # amount göndermiyoruz → exchange kapatır
        exchange.create_market_order(pos["sym"], side)

        bot.send_message(CHAT_ID, f"⛔ KAPANDI {pos['sym']} ({reason})")

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

                if time.time() - pos["open_time"] < 8:
                    continue

                price = exchange.fetch_ticker(pos["sym"])["last"]

                if pos["type"] == "LONG":
                    pnl = (price - pos["entry"]) / pos["entry"] * 30
                else:
                    pnl = (pos["entry"] - price) / pos["entry"] * 30

                if pnl > pos["max"]:
                    pos["max"] = pnl

                if pnl >= 0.70:
                    pos["trailing"] = True

                if pos["trailing"] and pos["max"] > 0.15:
                    if pnl < pos["max"] - 0.25:
                        close_trade(pos, "TRAILING", is_manual)

                if pnl <= -0.50:
                    close_trade(pos, "STOP LOSS", is_manual)

        except Exception as e:
            print("MANAGE ERROR:", e)

        time.sleep(2)

# ==============================
def clean_cache():
    global signal_cache
    while True:
        if len(signal_cache) > 100:
            signal_cache.clear()
        time.sleep(300)

# ==============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data.startswith("enter|"):
        key = call.data.split("|")[1]
        data = signal_cache.get(key)
        if data:
            open_trade(data, True)

# ==============================
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=manage, daemon=True).start()
threading.Thread(target=clean_cache, daemon=True).start()

bot.send_message(CHAT_ID, "💀 BOT AKTİF (FINAL STABLE)")
bot.infinity_polling()
