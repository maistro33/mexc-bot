import os, time, threading
import telebot
import ccxt

# ========= AYARLAR =========
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASS')

bot = telebot.TeleBot(TOKEN)

# ========= BORSAYA BAĞLAN =========
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

def safe(x):
    try:
        return float(x)
    except:
        return 0.0

# ========= BOT DURUM =========
bot_active = False
current_trade = None
grid_coin = None
last_trade_time = 0

# ========= PRO FIRSAT BULUCU =========
def find_pro_trade():
    exch = get_exch()
    markets = exch.load_markets()

    best = None
    best_score = 0

    for m in markets.values():
        sym = m['symbol']

        if ':USDT' not in sym:
            continue

        if any(x in sym for x in ['BTC','ETH','SOL']):
            continue

        try:
            ticker = exch.fetch_ticker(sym)
            change = safe(ticker.get('percentage',0))
            vol = safe(ticker.get('quoteVolume',0))

            if vol < 8000:
                continue

            if abs(change) < 6 or abs(change) > 25:
                continue

            side = 'long' if change < 0 else 'short'
            score = abs(change) * (vol / 10000)

            if score > best_score:
                best_score = score
                best = (sym, side)

        except:
            continue

    return best

# ========= İŞLEM AÇ =========
def open_trade(sym, side, usdt_amount):
    exch = get_exch()

    lev = 5
    try:
        exch.set_leverage(lev, sym)
    except:
        pass

    ticker = exch.fetch_ticker(sym)
    price = safe(ticker['last'])

    qty = (usdt_amount * lev) / price
    qty = float(exch.amount_to_precision(sym, qty))

    exch.create_market_order(sym, 'buy' if side == 'long' else 'sell', qty)

    bot.send_message(CHAT_ID, f"🐋 İşlem açıldı: {sym} {side.upper()} | Marjin: {usdt_amount:.2f}")

    return {'symbol': sym, 'side': side, 'entry': price, 'qty': qty, 'peak': 0}

# ========= KAR YÖNETİMİ =========
def manage_trade():
    global current_trade

    while True:
        if not bot_active or not current_trade:
            time.sleep(3)
            continue

        try:
            exch = get_exch()
            sym = current_trade['symbol']

            ticker = exch.fetch_ticker(sym)
            price = safe(ticker['last'])

            entry = current_trade['entry']
            side = current_trade['side']
            qty = current_trade['qty']

            profit = (price-entry)*qty if side=='long' else (entry-price)*qty

            if profit > current_trade['peak']:
                current_trade['peak'] = profit

            # STOP LOSS
            if profit <= -0.7:
                exch.create_market_order(sym,
                    'sell' if side=='long' else 'buy',
                    qty,
                    params={'reduceOnly':True})
                bot.send_message(CHAT_ID,"🛡️ Stop Loss")
                current_trade = None

            # TRAILING KAR
            elif current_trade['peak'] > 1.2 and (current_trade['peak']-profit) > 0.5:
                exch.create_market_order(sym,
                    'sell' if side=='long' else 'buy',
                    qty,
                    params={'reduceOnly':True})
                bot.send_message(CHAT_ID,f"💰 Kâr alındı: {profit:.2f}")
                current_trade = None

        except:
            pass

        time.sleep(2)

# ========= GRID =========
def setup_grid(sym):
    global grid_coin
    grid_coin = sym
    bot.send_message(CHAT_ID, f"🔹 Grid kuruldu: {sym}")

# ========= TELEGRAM KOMUTLARI =========
@bot.message_handler(func=lambda m: True)
def commands(message):
    global bot_active, current_trade, grid_coin, last_trade_time

    if str(message.chat.id) != str(CHAT_ID):
        return

    txt = message.text.lower()

    if txt == "startbot":
        bot_active = True
        bot.reply_to(message, "🐋 PRO BOT AKTİF")

    elif txt == "stopbot":
        bot_active = False
        bot.reply_to(message, "🛑 Bot durdu")

    elif txt == "durum":
        if current_trade:
            bot.reply_to(message, f"Açık işlem: {current_trade['symbol']} {current_trade['side']}")
        elif grid_coin:
            bot.reply_to(message, f"Grid aktif: {grid_coin}")
        else:
            bot.reply_to(message, "İşlem yok")

    # 🔥 İŞLEM ARA → BUL + AÇ
    elif txt == "islem ara":

        trade = find_pro_trade()

        if not trade:
            bot.reply_to(message, "Fırsat bulunamadı")
            return

        sym, side = trade

        exch = get_exch()
        bal = exch.fetch_balance({'type':'swap'})
        free_usdt = safe(bal['USDT']['free'])

        if free_usdt < 5:
            bot.reply_to(message, f"Bakiye yetersiz: {free_usdt:.2f} USDT")
            return

        bot.reply_to(message, f"🔎 Fırsat bulundu: {sym} {side}")

        current_trade = open_trade(sym, side, min(free_usdt*0.5, 6))
        last_trade_time = time.time()

    elif txt == "kapat" and current_trade:
        exch = get_exch()
        exch.create_market_order(
            current_trade['symbol'],
            'sell' if current_trade['side']=='long' else 'buy',
            current_trade['qty'],
            params={'reduceOnly':True}
        )
        bot.reply_to(message, "İşlem kapatıldı")
        current_trade = None

    elif txt.startswith("grid "):
        coin = txt.split()[1].upper()
        setup_grid(coin)

# ========= THREAD =========
threading.Thread(target=manage_trade, daemon=True).start()

bot.infinity_polling()
