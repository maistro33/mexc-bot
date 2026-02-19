import os, time, telebot, ccxt, threading, re
from google import genai

# --- BAĞLANTILAR ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

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

# --- AI BOT KURALI ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash ticaret dehasısın.
- Sadece altcoin, meme coin ve yeni çıkan coinleri analiz et.
- BTC, ETH, SOL gibi yüksek hacimli coinleri atla.
- Marjin ve kaldıraç bakiyeye göre otomatik ayarla.
- Stop-loss ve trailing kar seviyelerini USDT bazlı optimize et.
- Trailing sonuna kadar karı sömür.
- Telegram'a net mesaj ver: açtıysa ⚔️ İşlem açıldı, açılamadıysa sebebini yaz.
- Emir gelirse sadece dinle: kapat, ara, dur, başlat.
"""

# --- BOT AYARLARI ---
MAX_POSITIONS = 2
MIN_PROFIT_USDT = 0.8
TRAILING_GAP = 0.35
MIN_HOLD_SEC = 60
highest_profits = {}

# --- EMİR AÇMA ---
def open_trade(symbol, side):
    try:
        exch = get_exch()
        exch.load_markets()
        pos = exch.fetch_positions()
        active = [p for p in pos if safe_num(p.get('contracts'))>0]
        if len(active) >= MAX_POSITIONS:
            return "⚠️ Maksimum açık pozisyon"

        bal = exch.fetch_balance({'type':'swap'})
        free_usdt = safe_num(bal.get('USDT', {}).get('free',0))
        if free_usdt < 1:
            return f"⚠️ Bakiye yetersiz ({free_usdt:.2f} USDT)"

        amt_val = min(free_usdt*0.5,6)
        lev_val = 5

        exact_sym = next((s for s in exch.markets if symbol.upper() in s and ':USDT' in s), None)
        if not exact_sym: return f"⚠️ Coin bulunamadı: {symbol}"

        try: exch.set_leverage(lev_val, exact_sym)
        except: pass

        ticker = exch.fetch_ticker(exact_sym)
        last_price = safe_num(ticker['last'])
        qty = (amt_val * lev_val) / last_price
        min_qty = exch.markets[exact_sym]['limits']['amount']['min']
        qty = max(qty,min_qty)
        qty_precision = float(exch.amount_to_precision(exact_sym, qty))

        order = exch.create_market_order(exact_sym, 'buy' if side=='long' else 'sell', qty_precision)
        highest_profits[exact_sym] = 0
        order['openTime'] = time.time()
        bot.send_message(CHAT_ID, f"⚔️ İşlem açıldı: {exact_sym}\nYön: {side.upper()}\nMiktar: {amt_val} USDT\nKaldıraç: {lev_val}x\nID: {order['id']}")
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

                if time.time() - p['timestamp']/1000 < MIN_HOLD_SEC:
                    continue

                if sym not in highest_profits or profit>highest_profits[sym]:
                    highest_profits[sym]=profit

                stop_loss_usdt = max(0.5, 0.03*safe_num(p.get('margin'))*10)
                trailing_usdt = max(0.5, 0.05*safe_num(p.get('margin'))*10)

                # Stop-loss
                if profit <= -stop_loss_usdt:
                    exch.create_market_order(sym, 'sell' if side=='long' else 'buy', qty, params={'reduceOnly':True})
                    bot.send_message(CHAT_ID, f"🛡️ STOP LOSS: {sym} kapatıldı. Zararı: {profit:.2f} USDT")
                    highest_profits.pop(sym,None)

                # Trailing kar (sonuna kadar)
                elif highest_profits.get(sym,0) >= trailing_usdt and (highest_profits[sym]-profit)>=0.2:
                    exch.create_market_order(sym, 'sell' if side=='long' else 'buy', qty, params={'reduceOnly':True})
                    bot.send_message(CHAT_ID, f"💰 KAR ALINDI: {sym} {profit:.2f} USDT")
                    highest_profits.pop(sym,None)

            time.sleep(3)
        except: time.sleep(3)

# --- MARKET SCANNER + BALİNA MODU ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = [m['symbol'] for m in exch.load_markets().values()
                       if ':USDT' in m['symbol'] 
                       and all(x not in m['symbol'] for x in ['BTC','ETH','SOL'])
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
                bot.send_message(CHAT_ID,f"🤖 Analiz: {sym}, değişim skoru {s:.2f}")
                if s>1.5:
                    # AI kar odaklı, erken kapatma yok
                    execute_trade("",force=True,symbol=sym,side='long' if change_pct>0 else 'short')

            time.sleep(5)
        except: time.sleep(5)

# --- TELEGRAM KOMUTLARI: SENİN EMİRLERİNİ DİNLE ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    try:
        text = message.text.lower()

        if 'işlemi kapat' in text:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in pos:
                if safe_num(p.get('contracts'))>0:
                    exch.create_market_order(p['symbol'],'sell' if p['side']=='long' else 'buy',safe_num(p['contracts']),params={'reduceOnly':True})
                    bot.send_message(CHAT_ID,f"⚠️ Manuel kapatma: {p['symbol']} kapatıldı")
            return

        if 'işlem ara' in text:
            bot.send_message(CHAT_ID,"🔎 Bot yeni fırsatları arıyor...")

        if 'dur' in text:
            bot.send_message(CHAT_ID,"⏸️ Bot durduruldu")
            os._exit(0)

        if 'başlat' in text:
            bot.send_message(CHAT_ID,"▶️ Bot zaten çalışıyor...")

    except Exception as e:
        bot.reply_to(message,f"Sistem: {e}")

# --- BOT BAŞLAT ---
if __name__ == "__main__":
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.infinity_polling()
