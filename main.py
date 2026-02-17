import os, time, telebot, ccxt, threading, re
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

# --- [RUH VE TALİMATLAR] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget uzmanı, samimi ve zeki bir işlem dehasısın.
Kullanıcın senin dostun. Onunla samimi, dürüst ve heyecanlı konuş.
Ona piyasa analizleri yap, sorduğu sorulara benim (Gemini) tarzımla cevap ver.
İşlem yapman istendiğinde piyasayı tara ve en iyi fırsatı @@[ACTION: TRADE...]@@ formatıyla ver.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

# --- [YENİ: SENİ DİNLEYEN VE CEVAP VEREN KISIM] ---
@bot.message_handler(func=lambda message: True)
def handle_user_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    
    user_text = message.text
    try:
        exch = get_exch()
        balance = exch.fetch_balance()
        tickers = exch.fetch_tickers()
        
        # Kullanıcının sorusuna cevap verirken piyasa durumunu da bilmesi için:
        prompt = f"Kullanıcı dedi ki: '{user_text}'. \nCüzdan: {balance['free'].get('USDT', 0):.2f} USDT. Piyasa şu an hareketli. Ona samimi bir cevap ver ve eğer işlem yapmanı istiyorsa uygun bir @@[ACTION: TRADE...]@@ komutu oluştur."
        
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
        
        # Analizi gönder
        analysis = response.split("@@")[0].strip()
        safe_send(analysis)
        
        # Eğer işlem komutu varsa uygula
        if "@@" in response:
            execute_intelligence(response)
            
    except Exception as e:
        safe_send(f"Dostum bir sorun oldu: {str(e)}")

# --- [İŞLEM UYGULAMA MERKEZİ] ---
def execute_intelligence(decision):
    try:
        exch = get_exch()
        markets = exch.load_markets()
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                exact_sym = match.group(1).strip().upper()
                side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
                lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                if exact_sym in markets:
                    try: exch.set_leverage(lev_val, exact_sym)
                    except: pass
                    ticker = exch.fetch_ticker(exact_sym)
                    if (req_amt * lev_val) < 6: req_amt = 6.5 / lev_val
                    qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                    exch.create_order(exact_sym, 'market', side, qty)
                    safe_send(f"✅ *Emir Tamam:* {exact_sym} için daldım!")

        elif "@@[ACTION: CLOSE" in decision:
            pattern = r"@@\[ACTION: CLOSE,\s*([^\]]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                exact_sym = match.group(1).strip().upper()
                pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                if pos:
                    side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                    exch.create_order(exact_sym, 'market', side, float(pos[0]['contracts']), params={'reduceOnly': True})
                    safe_send(f"💰 *Kapatıldı:* {exact_sym} kârı alındı.")
    except Exception as e:
        safe_send(f"🚨 İşlem Hatası: {str(e)}")

# --- [OTONOM RADAR DÖNGÜSÜ] ---
def brain_loop():
    while True:
        try:
            exch = get_exch()
            markets = exch.load_markets()
            valid_symbols = [s for s in markets if markets[s]['swap'] and ':USDT' in s]
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage']} for s in valid_symbols if s in tickers], 
                          key=lambda x: abs(x['c']), reverse=True)[:10]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])
            prompt = f"Bakiye: {exch.fetch_balance()['free'].get('USDT', 0):.2f} USDT. \nRadar:\n{snapshot}\n\nDostuna bir piyasa güncellemesi yap ve bir fırsat varsa karar ver."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            analysis = response.split("@@")[0].strip()
            if analysis: safe_send(f"🧠 *OTONOM GÜNCELLEME:* \n{analysis}")
            if "@@" in response: execute_intelligence(response)
            
            time.sleep(60)
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    safe_send("🚀 *Gemini 3 Kulaklarını Açtı!* \nArtık hem piyasayı izliyorum hem de seninle sohbet etmeye hazırım. Ne dersen buradayım!")
    bot.infinity_polling()
