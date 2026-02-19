import os, time, threading
import telebot
import ccxt

# ================== AYARLAR ==================
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASS')

bot = telebot.TeleBot(TOKEN)

# ================== BORSAYA BAĞLAN ==================
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

# ================== BOT DURUM ==================
bot_active = False
current_trade = None
last_trade_time = 0
grid_trades = []

# ================== FIRSAT BULUCU (PRO SNIPER) ==================
def find_pro_trade():
    exch = get_exch()
    markets = exch.load_markets()
    best = None
    best_score = 0
    for m in markets.values():
        sym = m['symbol']
        if ':USDT' not in sym: continue
        if any(x in sym for x in ['BTC','ETH','SOL']): continue
        try:
            ticker = exch.fetch_ticker(sym)
            change = safe(ticker.get('percentage',0))
            vol = safe(ticker.get('quoteVolume',0))
            if vol < 8000: continue
            if abs(change) < 7: continue
            if abs(change) > 25: continue
            side = 'long' if change < 0 else 'short'
            score = abs(change)*(vol/10000)
            if score > best_score:
                best_score = score
                best = (sym, side)
        except: continue
    return best

# ================== GRID SEVİYELERİ ==================
GRID_LEVELS = 5   # Kaç seviye grid açılacak
GRID_RANGE = 0.03 # %3 aralık
GRID_SIZE = 0.5   # Bakiyenin %50'si her grid için

def setup_grid(sym):
    exch = get_exch()
    ticker = exch.fetch_ticker(sym)
    price = safe(ticker['last'])
    grid_trades.clear()
    for i in range(-GRID_LEVELS//2, GRID_LEVELS//2+1):
        level_price = price*(1 + i*GRID_RANGE)
        grid_trades.append({'symbol':sym, 'side':'long', 'price':level_price, 'filled':False})
    bot.send_message(CHAT_ID,f"🔹 Grid kuruldu: {sym} fiyat {price:.2f}")

# ================== İŞLEM AÇ ==================
def open_trade(sym, side, amount_usdt):
    exch = get_exch()
    lev = 5
    exch.set_leverage(lev, sym)
    ticker = exch.fetch_ticker(sym)
    price = safe(ticker['last'])
    qty = (amount_usdt*lev)/price
    qty = float(exch.amount_to_precision(sym, qty))
    exch.create_market_order(sym, 'buy' if side=='long' else 'sell', qty)
    bot.send_message(CHAT_ID,f"🐋 İşlem açıldı: {sym} {side.upper()} marjin: {amount_usdt:.2f}")
    return {'symbol':sym,'side':side,'entry':price,'qty':qty,'peak':0}

# ================== GRID İŞLEM KONTROL ==================
def grid_manager():
    global grid_trades
    while True:
        if not bot_active or not grid_trades: time.sleep(3); continue
        exch = get_exch()
        for g in grid_trades:
            if g['filled']: continue
            ticker = exch.fetch_ticker(g['symbol'])
            price = safe(ticker['last'])
            # Grid fiyatına geldiğinde al
            if (g['side']=='long' and price <= g['price']) or (g['side']=='short' and price >= g['price']):
                bal = exch.fetch_balance({'type':'swap'})
                free_usdt = safe(bal['USDT']['free'])
                if free_usdt < 5: continue
                open_trade(g['symbol'], g['side'], min(free_usdt*GRID_SIZE,5))
                g['filled'] = True
        time.sleep(5)

# ================== KAR YÖNETİMİ (PRO) ==================
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
            if profit <= -0.7:
                exch.create_market_order(sym,'sell' if side=='long' else 'buy',qty,params={'reduceOnly':True})
                bot.send_message(CHAT_ID,"🛡️ Stop Loss")
                current_trade = None
            elif current_trade['peak'] > 1.2 and (current_trade['peak']-profit)>0.5:
                exch.create_market_order(sym,'sell' if side=='long' else 'buy',qty,params={'reduceOnly':True})
                bot.send_message(CHAT_ID,f"💰 Kâr alındı: {profit:.2f}")
                current_trade = None
        except: pass
        time.sleep(2)

# ================== SNIPER (PRO) ==================
def hunter():
    global current_trade, last_trade_time
    while True:
        if bot_active and not current_trade:
            if time.time()-last_trade_time < 300: time.sleep(5); continue
            trade = find_pro_trade()
            if trade:
                bal = get_exch().fetch_balance({'type':'swap'})
                free_usdt = safe(bal['USDT']['free'])
                if free_usdt < 5: time.sleep(5); continue
                current_trade = open_trade(trade[0],trade[1],min(free_usdt*0.5,6))
                last_trade_time = time.time()
        time.sleep(10)

# ================== TELEGRAM KOMUTLARI ==================
@bot.message_handler(func=lambda m: True)
def commands(message):
    global bot_active, current_trade
    if str(message.chat.id) != str(CHAT_ID): return
    txt = message.text.lower()
    if txt=="startbot":
        bot_active=True
        bot.reply_to(message,"🐋 PRO+GRID BOT başladı")
    elif txt=="stopbot":
        bot_active=False
        bot.reply_to(message,"🛑 Bot durdu")
    elif txt=="durum":
        if current_trade: bot.reply_to(message,f"Açık işlem: {current_trade['symbol']}")
        else: bot.reply_to(message,"İşlem yok")
    elif txt=="kapat" and current_trade:
        exch=get_exch()
        exch.create_market_order(current_trade['symbol'],'sell' if current_trade['side']=='long' else 'buy',current_trade['qty'],params={'reduceOnly':True})
        bot.reply_to(message,"İşlem kapatıldı")
        current_trade=None
    elif txt=="islem ara":
        trade=find_pro_trade()
        if trade: bot.reply_to(message,f"Fırsat: {trade[0]} {trade[1]}")
        else: bot.reply_to(message,"Fırsat yok")
    elif txt.startswith("grid "):
        coin = txt.split()[1].upper()
        setup_grid(coin)

# ================== THREADLER ==================
threading.Thread(target=hunter,daemon=True).start()
threading.Thread(target=manage_trade,daemon=True).start()
threading.Thread(target=grid_manager,daemon=True).start()

bot.infinity_polling()
