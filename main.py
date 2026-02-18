import os, time, telebot, ccxt, threading, re
from google import genai

# ===== AYARLAR =====
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASS')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai = genai.Client(api_key=GEMINI_KEY)

# ===== BORSAYA BAĞLAN =====
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

# ===== TÜM COİNLERİ TARA =====
def scan_markets():
    exch = get_exch()
    exch.load_markets()

    best = None
    best_score = 0

    for s in exch.symbols:
        if "/USDT" in s and ":USDT" in s:
            try:
                t = exch.fetch_ticker(s)
                change = abs(t.get('percentage') or 0)
                vol = t.get('quoteVolume') or 0

                score = change * vol

                if score > best_score and vol > 1_000_000:
                    best_score = score
                    best = s
            except:
                pass

    return best

# ===== POZİSYON VAR MI =====
def has_position():
    exch = get_exch()
    pos = exch.fetch_positions()
    return any(float(p.get('contracts',0)) > 0 for p in pos)

# ===== İŞLEM AÇ =====
def open_trade(symbol):
    exch = get_exch()
    ticker = exch.fetch_ticker(symbol)
    price = ticker['last']

    balance = exch.fetch_balance({'type':'swap'})
    usdt = balance['USDT']['free']

    margin = usdt * 0.05  # bakiyenin %5'i
    lev = 10

    qty = (margin * lev) / price
    qty = float(exch.amount_to_precision(symbol, qty))

    exch.set_leverage(lev, symbol)
    order = exch.create_market_buy_order(symbol, qty)

    bot.send_message(CHAT_ID,
        f"⚔️ İşlem Açıldı\n{symbol}\nFiyat: {price}")

# ===== AV MODU =====
def hunter():
    while True:
        try:
            if not has_position():
                symbol = scan_markets()
                if symbol:
                    bot.send_message(CHAT_ID,
                        f"🎯 Fırsat bulundu: {symbol}")
                    open_trade(symbol)
            time.sleep(60)
        except:
            time.sleep(60)

# ===== POZİSYON YÖNETİMİ =====
def manager():
    highest = {}

    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()

            for p in pos:
                if float(p.get('contracts',0)) > 0:
                    sym = p['symbol']
                    roe = float(p.get('percentage') or 0)

                    if sym not in highest or roe > highest[sym]:
                        highest[sym] = roe

                    # STOP LOSS
                    if roe <= -5:
                        exch.create_market_sell_order(
                            sym, float(p['contracts']),
                            params={'reduceOnly':True})
                        bot.send_message(CHAT_ID,
                            f"🛑 STOP LOSS {sym}")

                    # TRAILING
                    elif highest[sym] >= 5 and \
                         highest[sym] - roe >= 2:
                        exch.create_market_sell_order(
                            sym, float(p['contracts']),
                            params={'reduceOnly':True})
                        bot.send_message(CHAT_ID,
                            f"💰 KAR ALINDI {sym}")

            time.sleep(10)
        except:
            time.sleep(10)

# ===== TELEGRAM SOHBET =====
@bot.message_handler(func=lambda m: True)
def talk(m):
    if str(m.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            bal = exch.fetch_balance({'type':'swap'})
            usdt = bal['USDT']['free']

            reply = f"""
💰 Bakiye: {usdt} USDT
🤖 Bot aktif
🔎 Sürekli fırsat arıyorum
"""
            bot.reply_to(m, reply)
        except:
            bot.reply_to(m, "Sistem hatası")

# ===== BAŞLAT =====
if __name__ == "__main__":
    threading.Thread(target=hunter, daemon=True).start()
    threading.Thread(target=manager, daemon=True).start()
    bot.infinity_polling()
