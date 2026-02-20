import os, time, telebot, ccxt, threading, re

# --- BAĞLANTILAR ---
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"

bot = telebot.TeleBot(TELE_TOKEN)

# --- EXCHANGE ---
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

def safe_num(val):
    try:
        if val is None: return 0.0
        clean = re.sub(r'[^0-9.]', '', str(val).replace(',', '.'))
        return float(clean) if clean else 0.0
    except: return 0.0

# --- SABİT AYARLAR ---
MAX_POSITIONS = 2
MARGIN_PER_TRADE = 2
LEVERAGE = 5
STOP_LOSS_PERCENT = 0.05
TAKE_PROFIT_PERCENT = 0.03
TRAILING_PERCENT = 0.015
highest_profits = {}
MIN_HOLD_SEC = 60
open_coins = set()
lock = threading.Lock()

# --- EMİR AÇMA ---
def open_trade(symbol, side):
    with lock:
        if symbol in open_coins:
            return f"⚠️ {symbol} zaten işlemde veya tamamlandı"

        try:
            exch = get_exch()
            exch.load_markets()
            pos = exch.fetch_positions()
            active = [p for p in pos if safe_num(p.get('contracts'))>0]
            if len(active) >= MAX_POSITIONS:
                return "⚠️ Maksimum açık pozisyon"

            bal = exch.fetch_balance({'type':'swap'})
            free_usdt = safe_num(bal.get('USDT', {}).get('free',0))
            if free_usdt < MARGIN_PER_TRADE:
                return f"⚠️ Bakiye yetersiz ({free_usdt:.2f} USDT)"

            exact_sym = next((s for s in exch.markets if symbol.upper() in s and ':USDT' in s), None)
            if not exact_sym: return f"⚠️ Coin bulunamadı: {symbol}"

            try: exch.set_leverage(LEVERAGE, exact_sym)
            except: pass

            ticker = exch.fetch_ticker(exact_sym)
            last_price = safe_num(ticker['last'])
            qty = (MARGIN_PER_TRADE * LEVERAGE) / last_price
            min_qty = exch.markets[exact_sym]['limits']['amount']['min']
            qty = max(qty,min_qty)
            qty_precision = float(exch.amount_to_precision(exact_sym, qty))

            order_price = last_price * 0.999 if side=='long' else last_price*1.001
            order = exch.create_limit_order(exact_sym, 'buy' if side=='long' else 'sell', qty_precision, order_price)
            highest_profits[exact_sym] = 0
            open_coins.add(symbol)
            order['openTime'] = time.time()
            bot.send_message(MY_CHAT_ID, f"⚔️ İşlem açıldı: {exact_sym}\nYön: {side.upper()}\nMiktar: {MARGIN_PER_TRADE} USDT\nKaldıraç: {LEVERAGE}x\nID: {order['id']}")
            return f"⚔️ İşlem açıldı: {exact_sym}"

        except Exception as e:
            return f"⚠️ HATA: {str(e)}"

# --- TRAILING + KAR YÖNETİMİ ---
def auto_manager():
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in [p for p in pos if safe_num(p.get('contracts'))>0]:
                sym = p['symbol']
                side = p['side']
                qty = safe_num(p.get('contracts'))
                entry = safe_num(p.get('entryPrice'))
                ticker = exch.fetch_ticker(sym)
                last = safe_num(ticker['last'])
                profit = (last-entry)*qty if side=='long' else (entry-last)*qty

                if time.time() - p.get('timestamp',0)/1000 < MIN_HOLD_SEC:
                    continue

                if sym not in highest_profits or profit>highest_profits[sym]:
                    highest_profits[sym]=profit

                stop_loss_usdt = max(0.5, STOP_LOSS_PERCENT*safe_num(p.get('margin'))*10)
                trailing_usdt = max(0.5, TRAILING_PERCENT*safe_num(p.get('margin'))*10)

                if profit <= -stop_loss_usdt:
                    exch.create_market_order(sym, 'sell' if side=='long' else 'buy', qty, params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID, f"🛡️ STOP LOSS: {sym} kapatıldı. Zararı: {profit:.2f} USDT")
                    highest_profits.pop(sym,None)
                    open_coins.discard(sym)

                elif highest_profits.get(sym,0) >= trailing_usdt and (highest_profits[sym]-profit)>=0.2:
                    exch.create_market_order(sym, 'sell' if side=='long' else 'buy', qty, params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID, f"💰 KAR ALINDI: {sym} {profit:.2f} USDT")
                    highest_profits.pop(sym,None)
                    open_coins.discard(sym,None)

            time.sleep(3)
        except:
            time.sleep(3)

# --- MARKET SCANNER ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            all_markets = exch.load_markets().values()

            # Sadece yeni/meme coinler ve yüksek volatilite, büyük coinleri atla
            markets = []
            for m in all_markets:
                sym = m['symbol']
                quote_vol = safe_num(m.get('quoteVolume',0))
                if ':USDT' not in sym: 
                    continue
                if any(x in sym for x in ['BTC','ETH','XRP','SOL']):  # büyük coinleri atla
                    continue
                if quote_vol < 1000:  # çok düşük hacimli coinleri atla
                    continue
                markets.append(m)

            # Telegram'a analiz edilen coinleri gönder
            analyzed_coins = [m['symbol'] for m in markets if m['symbol'] not in open_coins]
            if analyzed_coins:
                bot.send_message(MY_CHAT_ID, f"🔍 Analiz edilen coinler: {', '.join(analyzed_coins[:10])}...")

            # Scoring ve işlem açma
            scores = []
            for m in markets:
                sym = m['symbol']
                if sym in open_coins:
                    continue
                ticker = exch.fetch_ticker(sym)
                change_pct = safe_num(ticker.get('percentage',0))
                volume = safe_num(ticker.get('quoteVolume',0))
                normalized_volume = min(volume,50000)
                score = (change_pct*0.7)+(normalized_volume/1000*0.3)
                if volume<1000: score*=1.2
                scores.append((score,sym,change_pct))

            scores.sort(reverse=True)
            top = scores[:2]
            for s,sym,change_pct in top:
                if s>1.5:
                    open_trade(sym,'long' if change_pct>0 else 'short')

            time.sleep(5)
        except:
            time.sleep(5)

# --- TELEGRAM KOMUTLARI ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) != str(MY_CHAT_ID): return
    try:
        text = message.text.lower()
        if text.startswith('/open '):
            coin = text.split('/open ')[1].upper()
            bot.send_message(MY_CHAT_ID, open_trade(coin,'long'))

        if 'işlemi kapat' in text:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in pos:
                if safe_num(p.get('contracts'))>0:
                    exch.create_market_order(p['symbol'],'sell' if p['side']=='long' else 'buy',safe_num(p['contracts']),params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID,f"⚠️ Manuel kapatma: {p['symbol']} kapatıldı")
                    open_coins.discard(p['symbol'])
            return

        if 'dur' in text:
            bot.send_message(MY_CHAT_ID,"⏸️ Bot durduruldu")
            os._exit(0)

        if 'başlat' in text:
            bot.send_message(MY_CHAT_ID,"▶️ Bot zaten çalışıyor...")

    except Exception as e:
        bot.reply_to(message,f"Sistem: {e}")

# --- BOT BAŞLAT ---
if __name__ == "__main__":
    bot.send_message(MY_CHAT_ID,"🤖 Bot başlatıldı ve çalışıyor ✅")
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.infinity_polling()
