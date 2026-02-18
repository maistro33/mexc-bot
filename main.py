import os, time, telebot, ccxt, threading, re, random

# ===== AYARLAR =====
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"  # Sabit

bot = telebot.TeleBot(TOKEN)
RUN_BOT = True  # Telegram ile durdur/başlat

# ===== YARDIMCI FONKSİYON =====
def safe_num(val):
    try:
        return float(re.sub(r'[^0-9.]', '', str(val).replace(',', '.')))
    except:
        return 0.0

# ===== BORSA BAĞLANTI =====
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

# ===== POZİSYON KONTROL =====
def has_position(symbol=None):
    exch = get_exch()
    pos = exch.fetch_positions()
    for p in pos:
        if safe_num(p.get('contracts',0))>0:
            if symbol and symbol.upper() not in p['symbol']:
                continue
            return True, p
    return False, None

# ===== PİYASA TARAMA =====
def scan_markets():
    exch = get_exch()
    exch.load_markets()
    best = None
    best_score = 0
    best_change = 0

    for s in exch.symbols:
        if s.endswith(":USDT"):
            try:
                t = exch.fetch_ticker(s)
                change = abs(safe_num(t.get('percentage',0)))
                vol = safe_num(t.get('quoteVolume',0))
                if change>20 or vol<500000:  # pump / düşük hacim filtre
                    continue
                score = change*vol
                if score>best_score:
                    best_score=score
                    best=s
                    best_change=change
            except:
                continue
    if best:
        bot.send_message(CHAT_ID,f"🤖 Analiz: En iyi fırsat {best}, değişim %{best_change:.2f}.")
    return best

# ===== İŞLEM AÇMA =====
def open_trade(symbol):
    exch = get_exch()
    ticker = exch.fetch_ticker(symbol)
    price = safe_num(ticker['last'])
    balance = exch.fetch_balance({'type':'swap'})
    usdt = safe_num(balance.get('USDT',{}).get('free',0))
    margin = max(10, usdt*0.05)  # minimum 10 USDT
    lev = 10
    qty = (margin*lev)/price
    qty = float(exch.amount_to_precision(symbol, qty))
    min_profit = margin*lev*0.0006*2

    bot.send_message(CHAT_ID,f"📈 Fırsat tespit edildi.\n🎯 {symbol}\nFiyat: {price}\nMarjin: {margin:.2f} USDT\nMiktar: {qty}\nMin Kâr: {min_profit:.4f}")

    try:
        exch.set_leverage(lev, symbol)
        order = exch.create_market_buy_order(symbol, qty)
    except Exception as e:
        bot.send_message(CHAT_ID,f"❌ İşlem Hatası: {str(e)}")

# ===== HUNTER MOD =====
def hunter_mode():
    while True:
        try:
            if RUN_BOT:
                has_pos, _ = has_position()
                if not has_pos:
                    symbol = scan_markets()
                    if symbol:
                        open_trade(symbol)
            time.sleep(30)
        except Exception as e:
            bot.send_message(CHAT_ID,f"❌ Tarama Hatası: {str(e)}")
            time.sleep(30)

# ===== MANAGER MOD =====
def manager_mode():
    highest = {}
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in pos:
                contracts = safe_num(p.get('contracts',0))
                if contracts>0:
                    sym = p['symbol']
                    roe = safe_num(p.get('percentage',0))
                    if sym not in highest or roe>highest[sym]:
                        highest[sym]=roe
                    if roe<=-5:
                        exch.create_market_sell_order(sym, contracts, params={'reduceOnly':True})
                        bot.send_message(CHAT_ID,f"🛑 STOP LOSS {sym}")
                    elif highest[sym]>=5 and (highest[sym]-roe)>=2:
                        exch.create_market_sell_order(sym, contracts, params={'reduceOnly':True})
                        bot.send_message(CHAT_ID,f"💰 KAR ALINDI {sym}")
            time.sleep(10)
        except Exception as e:
            bot.send_message(CHAT_ID,f"❌ Manager Hatası: {str(e)}")
            time.sleep(10)

# ===== TELEGRAM KOMUTLARI =====
@bot.message_handler(commands=['startbot'])
def start_bot(message):
    global RUN_BOT
    RUN_BOT = True
    bot.reply_to(message,"🤖 Bot çalışmaya başladı.")

@bot.message_handler(commands=['stopbot'])
def stop_bot(message):
    global RUN_BOT
    RUN_BOT = False
    bot.reply_to(message,"🛑 Bot durduruldu.")

@bot.message_handler(commands=['balance'])
def balance(message):
    exch = get_exch()
    bal = exch.fetch_balance({'type':'swap'})
    usdt = safe_num(bal.get('USDT',{}).get('free',0))
    bot.reply_to(message,f"💰 Bakiye: {usdt} USDT")

@bot.message_handler(commands=['open'])
def manual_open(message):
    parts = message.text.split()
    if len(parts)==2:
        symbol = parts[1].upper()
        if not symbol.endswith(":USDT"):
            symbol+=":USDT"
        open_trade(symbol)
    else:
        bot.reply_to(message,"Kullanım: /open BTC → BTC/USDT işlem açar")

@bot.message_handler(commands=['check'])
def check_position(message):
    parts = message.text.split()
    if len(parts)==2:
        symbol = parts[1].upper()
        if not symbol.endswith(":USDT"):
            symbol+=":USDT"
        has_pos, p = has_position(symbol)
        if has_pos:
            bot.reply_to(message,f"🤖 {symbol}: Açık pozisyon var ✅\nYön: {p['side']}\nMiktar: {p['contracts']}\nROE: %{safe_num(p.get('percentage',0)):.2f}\nTP/SL: Aktif\nTrailing: Aktif")
        else:
            bot.reply_to(message,f"🤖 {symbol}: Açık pozisyon yok ❌")
    else:
        bot.reply_to(message,"Kullanım: /check BTC → BTC/USDT pozisyon kontrolü")

# ===== AKILLI SOHBET =====
@bot.message_handler(func=lambda m: True)
def chat_ai(message):
    msg = message.text.lower()
    if "selam" in msg or "merhaba" in msg:
        bot.reply_to(message,"🤖 Selam Sadık! Piyasayı tarıyorum, fırsat olursa haber veririm.")
    elif "ne yapıyorsun" in msg or "nasıl" in msg:
        bot.reply_to(message,"🤖 Şu anda piyasayı tarıyorum ve en iyi fırsatları buluyorum.")
    elif "fiyat" in msg or "borsa" in msg:
        bot.reply_to(message,"🤖 En iyi scalp fırsatını bulup sana bildireceğim.")
    else:
        bot.reply_to(message,"🤖 Anladım, piyasayı gözlemliyorum ve fırsat olursa bildireceğim.")

bot.send_message(CHAT_ID,"🤖 Ultra Scalp AI Bot aktif ve hazır! Telegram üzerinden konuşabilirsiniz.")

# ===== BAŞLAT =====
threading.Thread(target=hunter_mode,daemon=True).start()
threading.Thread(target=manager_mode,daemon=True).start()
bot.infinity_polling()
