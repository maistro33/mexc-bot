import os, time, telebot, ccxt, threading, re
from google import genai

# --- BAĞLANTILAR ---
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TELE_TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- SABİT AYARLAR ---
MARGIN_PER_TRADE = 6  # her işlem için sabit USDT
LEVERAGE = 5
MAX_POSITIONS = 2
MIN_HOLD_SEC = 30  # pozisyonun açıldıktan sonra minimum bekleme süresi
STOP_LOSS_RATIO = 0.10  # %10 kayıp toleransı
TRAILING_RATIO = 0.20   # %20 kar gelirse takip et

highest_profits = {}

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
    except:
        return 0.0

# --- POZİSYON AÇMA ---
def open_trade(symbol, side):
    try:
        exch = get_exch()
        exch.load_markets()
        pos = exch.fetch_positions()
        active = [p for p in pos if safe_num(p.get('contracts'))>0]
        if len(active) >= MAX_POSITIONS:
            return "⚠️ Maksimum açık pozisyon"

        exact_sym = next((s for s in exch.markets if symbol.upper() in s and ':USDT' in s), None)
        if not exact_sym:
            return f"⚠️ Coin bulunamadı: {symbol}"

        ticker = exch.fetch_ticker(exact_sym)
        last_price = safe_num(ticker['last'])
        low_price = safe_num(ticker['low'])

        # Dipten giriş kontrolü
        if last_price > low_price*1.01:  # %1 farkla dipten giriş
            return f"⚠️ {symbol} fiyatı uygun değil, dipten giriş bekleniyor"

        qty = (MARGIN_PER_TRADE * LEVERAGE) / last_price
        min_qty = exch.markets[exact_sym]['limits']['amount']['min']
        qty = max(qty,min_qty)
        qty_precision = float(exch.amount_to_precision(exact_sym, qty))

        try: exch.set_leverage(LEVERAGE, exact_sym)
        except: pass

        order = exch.create_market_order(exact_sym, 'buy' if side=='long' else 'sell', qty_precision)
        highest_profits[exact_sym] = 0
        order['openTime'] = time.time()
        bot.send_message(MY_CHAT_ID, f"⚔️ İşlem açıldı: {exact_sym}\nYön: {side.upper()}\nMiktar: {MARGIN_PER_TRADE} USDT\nKaldıraç: {LEVERAGE}x\nID: {order['id']}")
        return f"⚔️ İşlem açıldı: {exact_sym}"
    except Exception as e:
        return f"⚠️ HATA: {str(e)}"

# --- TRAILING + STOP-LOSS YÖNETİMİ ---
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

                # Minimum pozisyon bekleme süresi
                if time.time() - p.get('timestamp',0)/1000 < MIN_HOLD_SEC:
                    continue

                if sym not in highest_profits or profit>highest_profits[sym]:
                    highest_profits[sym]=profit

                stop_loss_usdt = max(0.5, STOP_LOSS_RATIO*MARGIN_PER_TRADE)
                trailing_usdt = max(0.5, TRAILING_RATIO*MARGIN_PER_TRADE)

                # STOP-LOSS
                if profit <= -stop_loss_usdt:
                    exch.create_market_order(sym, 'sell' if side=='long' else 'buy', qty, params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID, f"🛡️ STOP LOSS: {sym} kapatıldı. Zararı: {profit:.2f} USDT")
                    highest_profits.pop(sym,None)

                # TRAILING KAR
                elif highest_profits.get(sym,0) >= trailing_usdt and (highest_profits[sym]-profit) >= 0.2:
                    exch.create_market_order(sym, 'sell' if side=='long' else 'buy', qty, params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID, f"💰 KAR ALINDI: {sym} {profit:.2f} USDT")
                    highest_profits.pop(sym,None)

            time.sleep(3)
        except:
            time.sleep(3)

# --- MARKET SCANNER ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = [m['symbol'] for m in exch.load_markets().values()
                       if ':USDT' in m['symbol'] and all(x not in m['symbol'] for x in ['BTC','ETH','SOL'])
                       and safe_num(m.get('quoteVolume',0)) < 100_000]

            scores = []
            for sym in markets:
                ticker = exch.fetch_ticker(sym)
                change_pct = safe_num(ticker.get('percentage',0))
                volume = safe_num(ticker.get('quoteVolume',0))
                normalized_volume = min(volume,50000)
                score = (change_pct*0.7)+(normalized_volume/1000*0.3)
                if volume<1000: score*=1.2
                scores.append((score,sym))

            scores.sort(reverse=True)
            top = scores[:5]
            for s,sym in top:
                bot.send_message(MY_CHAT_ID,f"🤖 Analiz: {sym}, değişim skoru {s:.2f}")
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

        if 'işlemi kapat' in text:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in pos:
                if safe_num(p.get('contracts'))>0:
                    exch.create_market_order(p['symbol'],'sell' if p['side']=='long' else 'buy',safe_num(p['contracts']),params={'reduceOnly':True})
                    bot.send_message(MY_CHAT_ID,f"⚠️ Manuel kapatma: {p['symbol']} kapatıldı")
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
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.infinity_polling()
