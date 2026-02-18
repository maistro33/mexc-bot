import os, time, telebot, ccxt, threading

TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TOKEN)

MANUAL_LOCK = False

# ===== EXCHANGE =====
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

# ===== İŞLEM AÇ =====
def open_trade(symbol, side):
    try:
        exch = get_exch()
        exch.load_markets()

        exact = next((s for s in exch.markets if symbol.upper() in s and ':USDT' in s), None)
        if not exact:
            bot.send_message(CHAT_ID, "Coin bulunamadı")
            return

        leverage = 10
        margin = 10

        exch.set_leverage(leverage, exact)

        ticker = exch.fetch_ticker(exact)
        price = ticker['last']

        qty = (margin * leverage) / price
        qty = float(exch.amount_to_precision(exact, qty))

        order_side = 'buy' if side == 'long' else 'sell'
        exch.create_market_order(exact, order_side, qty)

        bot.send_message(CHAT_ID,
            f"⚔️ İŞLEM AÇILDI\n{exact}\n{side.upper()}")

    except Exception as e:
        bot.send_message(CHAT_ID, f"Hata: {e}")

# ===== AKILLI FIRSAT BULUCU =====
def find_safe_trade():
    exch = get_exch()
    markets = [m['symbol'] for m in exch.load_markets().values()
               if ':USDT' in m['symbol'] and 'swap' in m['type']]

    best = None
    best_score = 0
    best_side = "long"

    for sym in markets:
        t = exch.fetch_ticker(sym)

        change = abs(t.get('percentage', 0))
        volume = t.get('quoteVolume', 0)
        high = t.get('high', 0)
        low = t.get('low', 0)
        last = t.get('last', 0)

        if not last or not volume:
            continue

        volatility = (high - low) / last

        # 🎯 SADECE KALİTELİ FIRSATLAR
        if volatility < 0.01 or volume < 100000:
            continue

        score = change * volatility * volume

        if score > best_score:
            best_score = score
            best = sym
            best_side = "long" if t.get('percentage',0) > 0 else "short"

    return best, best_side

# ===== OTOMATİK =====
def auto_trader():
    global MANUAL_LOCK

    while True:
        if MANUAL_LOCK:
            time.sleep(10)
            continue

        try:
            sym, side = find_safe_trade()

            if sym:
                bot.send_message(CHAT_ID,
                    f"🤖 Güçlü fırsat: {sym} → {side.upper()}")

                open_trade(sym.split('/')[0], side)

            else:
                bot.send_message(CHAT_ID, "Beklemede. Kaliteli fırsat yok.")

            time.sleep(60)

        except:
            time.sleep(20)

# ===== TP / SL =====
def risk_manager():
    highest = {}

    while True:
        try:
            exch = get_exch()
            positions = exch.fetch_positions()

            for p in positions:
                if float(p.get('contracts',0)) <= 0:
                    continue

                sym = p['symbol']
                roe = float(p.get('percentage',0))

                if sym not in highest or roe > highest[sym]:
                    highest[sym] = roe

                # STOP LOSS
                if roe <= -6:
                    exch.create_market_order(sym,
                        'sell' if p['side']=='long' else 'buy',
                        float(p['contracts']),
                        params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ STOP LOSS {sym}")

                # KAR AL
                if highest[sym] >= 5 and highest[sym] - roe >= 2:
                    exch.create_market_order(sym,
                        'sell' if p['side']=='long' else 'buy',
                        float(p['contracts']),
                        params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"💰 KAR ALINDI {sym}")

            time.sleep(5)

        except:
            time.sleep(5)

# ===== TELEGRAM =====
@bot.message_handler(func=lambda m: True)
def handle(m):
    global MANUAL_LOCK

    if str(m.chat.id) != str(CHAT_ID):
        return

    txt = m.text.lower()

    if "ac" in txt:
        parts = txt.split()
        coin = parts[0].upper()

        side = "long"
        if "short" in txt:
            side = "short"

        MANUAL_LOCK = True
        open_trade(coin, side)

    if "auto" in txt:
        MANUAL_LOCK = False
        bot.send_message(CHAT_ID, "Otomatik moda dönüldü")

# ===== START =====
if __name__ == "__main__":
    threading.Thread(target=auto_trader, daemon=True).start()
    threading.Thread(target=risk_manager, daemon=True).start()
    bot.infinity_polling()
