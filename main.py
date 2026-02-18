import os, time, telebot, ccxt, threading, re, json
from google import genai

# --- [BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [EXCHANGE BAĞLANTISI] ---
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_num(val):
    try:
        if val is None: return 0.0
        clean = re.sub(r'[^0-9.]', '', str(val).replace(',', '.'))
        return float(clean) if clean else 0.0
    except: return 0.0

# --- [ULTRA SCALP DEHA AYARI] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın ticaret dehası yansımasıısın. 
1. KURAL: Asla yalan söyleme. İşlem açmadıysan 'Beklemede' de.
2. EMİR: Bir fırsat gördüğünde mutlaka @@[ACTION: TRADE, SEMBOL, YON, KALDIRAC, MARJIN]@@ formatını kullan.
3. ÖRNEK: @@[ACTION: TRADE, BTC, SHORT, 10, 10]@@
4. SCALP BOT: Pump ve momentumları yakala, TP/SL/Trailing gizli uygula, karı maksimum al.
"""

# --- [İŞLEM AÇMA] ---
def execute_trade(symbol, side, lev=10, margin=10):
    try:
        exch = get_exch()
        exch.load_markets()
        exact_sym = next((s for s in exch.markets if symbol in s and ':USDT' in s), None)
        if not exact_sym: return f"⚠️ Sembol bulunamadı: {symbol}"
        
        side_str = 'sell' if side.upper() in ['SHORT', 'SELL'] else 'buy'
        ticker = exch.fetch_ticker(exact_sym)
        last_price = safe_num(ticker['last'])
        qty = (margin * lev) / last_price
        qty_precision = float(exch.amount_to_precision(exact_sym, qty))

        # Kaldıraç
        try: exch.set_leverage(lev, exact_sym)
        except: pass

        # Market emri
        order = exch.create_market_order(exact_sym, side_str, qty_precision)

        return f"⚔️ **İŞLEM AÇILDI**\nSembol: {exact_sym}\nYön: {side_str.upper()}\nFiyat: {last_price}\nMarjin: {margin} USDT\nMiktar: {qty_precision}"
    except Exception as e:
        return f"⚠️ Borsa hatası: {str(e)}"

# --- [OTOMATİK YÖNETİCİ: TP / SL / TRAILING] ---
def auto_manager():
    highest_roes = {}
    while True:
        try:
            exch = get_exch()
            positions = exch.fetch_positions()
            for p in [p for p in positions if safe_num(p.get('contracts')) > 0]:
                sym = p['symbol']; roe = safe_num(p.get('percentage'))
                if sym not in highest_roes or roe > highest_roes[sym]: highest_roes[sym] = roe
                # Stop loss
                if roe <= -7.0:
                    exch.create_market_order(sym, ('sell' if p['side']=='long' else 'buy'), safe_num(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ STOP LOSS: {sym} kapatıldı")
                # Trailing kar
                elif highest_roes.get(sym,0)>=5.0 and (highest_roes[sym]-roe)>=2.0:
                    exch.create_market_order(sym, ('sell' if p['side']=='long' else 'buy'), safe_num(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"💰 KAR ALINDI: {sym} %{roe:.2f}")
            time.sleep(5)
        except:
            time.sleep(5)

# --- [TELEGRAM KOMUTLARI VE SOHBET] ---
@bot.message_handler(commands=['startbot'])
def start_bot(message):
    if str(message.chat.id) == str(CHAT_ID):
        bot.reply_to(message, "🤖 Bot başlatıldı, piyasayı tarıyorum.")

@bot.message_handler(commands=['stopbot'])
def stop_bot(message):
    if str(message.chat.id) == str(CHAT_ID):
        bot.reply_to(message, "🛑 Bot durduruldu.")

@bot.message_handler(commands=['balance'])
def balance(message):
    if str(message.chat.id) == str(CHAT_ID):
        exch = get_exch()
        bal = exch.fetch_balance({'type':'swap'})
        free_usdt = safe_num(bal.get('USDT', {}).get('free',0))
        bot.reply_to(message, f"💰 Cüzdan bakiyesi: {free_usdt} USDT")

@bot.message_handler(func=lambda m: True)
def handle_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    text = message.text.lower()
    if 'scalp işlem aç' in text:
        bot.reply_to(message, "🤖 Analiz başlatılıyor, en iyi fırsat aranıyor...")
        exch = get_exch()
        exch.load_markets()
        best_symbol = None
        best_score = -1000
        for sym in exch.symbols:
            if ':USDT' not in sym: continue
            ticker = exch.fetch_ticker(sym)
            change = safe_num(ticker.get('percentage',0))
            if change > best_score:
                best_score = change
                best_symbol = sym.replace(':USDT','')
        if best_symbol:
            res = execute_trade(best_symbol,'LONG',lev=10,margin=10)
            bot.send_message(CHAT_ID,res)
        else:
            bot.send_message(CHAT_ID,"⚠️ Fırsat bulunamadı.")
    else:
        bot.reply_to(message,"🤖 Piyasayı tarıyorum, fırsat olursa haber veririm.")

# --- [BOTU BAŞLAT] ---
if __name__ == "__main__":
    threading.Thread(target=auto_manager, daemon=True).start()
    bot.infinity_polling()
