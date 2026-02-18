import os, time, telebot, ccxt, threading, re, math

# ===== AYARLAR =====
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"  # Sabit

bot = telebot.TeleBot(TOKEN)

RUN_BOT = True  # Telegram ile durdur/başlat için global flag

def safe_num(val):
    try:
        return float(re.sub(r'[^0-9.]', '', str(val).replace(',', '.')))
    except:
        return 0.0

# ===== BORSAYA BAĞLAN =====
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

# ===== POZİSYON VAR MI =====
def has_position():
    exch = get_exch()
    pos = exch.fetch_positions()
    return any(safe_num(p.get('contracts',0)) > 0 for p in pos)

# ===== TÜM COİNLERİ TARA =====
def scan_markets():
    exch = get_exch()
    exch.load_markets()
    best = None
    best_score = 0

    for s in exch.symbols:
        if s.endswith(":USDT"):
            try:
                t = exch.fetch_ticker(s)
                change = abs(safe_num(t.get('percentage',0)))
                vol = safe_num(t.get('quoteVolume',0))
                if change > 20 or vol < 500000:  # sahte pump/likidite tuzak filtresi
                    continue
                score = change * vol
                if score > best_score:
                    best_score = score
                    best = s
            except:
                continue
    return best

# ===== İŞLEM AÇ =====
def open_trade(symbol):
    exch = get_exch()
    ticker = exch.fetch_ticker(symbol)
    price = safe_num(ticker['last'])

    balance = exch.fetch_balance({'type':'swap'})
    usdt = safe_num(balance.get('USDT', {}).get('free',0))

    margin = usdt * 0.05
    if margin < 10:
        bot.send_message(CHAT_ID,"💸 Minimum 10 USDT ile işlem açılır. Mevcut bakiye yeterli değil.")
        return

    lev = 10
    qty = (margin * lev) / price
    qty = float(exch.amount_to_precision(symbol, qty))

    fee_rate = 0.0006  # komisyon
    min_profit = margin * lev * fee_rate * 2

    try:
        exch.set_leverage(lev, symbol)
        order = exch.create_market_buy_order(symbol, qty)
        bot.send_message(CHAT_ID,
            f"🎯 Fırsat bulundu: {symbol}\n⚔️ İşlem Açıldı\nFiyat: {price}\nMarjin: {margin} USDT\nMiktar: {qty}\nMin Kâr: {min_profit:.4f}")
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ İşlem Hatası: {str(e)}")

# ===== AV MODU =====
def hunter_mode():
    while True:
        try:
            if RUN_BOT and not has_position():
                symbol = scan_markets()
                if symbol:
                    open_trade(symbol)
            time.sleep(30)
        except Exception as e:
            bot.send_message(CHAT_ID,f"❌ Tarama Hatası: {str(e)}")
            time.sleep(30)

# ===== POZİSYON YÖNETİMİ =====
def manager_mode():
    highest = {}
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in pos:
                contracts = safe_num(p.get('contracts',0))
                if contracts > 0:
                    sym = p['symbol']
                    roe = safe_num(p.get('percentage',0))

                    if sym not in highest or roe > highest[sym]:
                        highest[sym] = roe

                    # STOP LOSS
                    if roe <= -5:
                        exch.create_market_sell_order(sym, contracts, params={'reduceOnly':True})
                        bot.send_message(CHAT_ID, f"🛑 STOP LOSS {sym}")

                    # TRAILING KAR AL
                    elif highest[sym] >= 5 and (highest[sym]-roe)>=2:
                        exch.create_market_sell_order(sym, contracts, params={'reduceOnly':True})
                        bot.send_message(CHAT_ID, f"💰 KAR ALINDI {sym}")

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
    usdt = safe_num(bal.get('USDT', {}).get('free',0))
    bot.reply_to(message,f"💰 Bakiye: {usdt} USDT")

@bot.message_handler(commands=['open'])
def manual_open(message):
    parts = message.text.split()
    if len(parts) == 2:
        symbol = parts[1].upper()
        if not symbol.endswith(":USDT"):
            symbol += ":USDT"
        open_trade(symbol)
    else:
        bot.reply_to(message,"Kullanım: /open BTC → BTC/USDT işlem açar")

# ===== BAŞLAT =====
if __name__ == "__main__":
    threading.Thread(target=hunter_mode, daemon=True).start()
    threading.Thread(target=manager_mode, daemon=True).start()
    bot.infinity_polling()
