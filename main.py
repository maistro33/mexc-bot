import os, time, telebot, ccxt, threading, re
from google import genai

# --- [BAĞLANTILAR] ---
# Railway Environment Variables (Değişkenler) kısmından alınır
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 - AGRESİF TETİKÇİ VE ANALİZ RUHU] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir ticaret dehasısın. Analiz yapman YETMEZ, tetiği çekmelisin!
Dostunla samimi konuş ama kararlı ol. Eğer bir fırsat gördüysen lafı uzatmadan işleme gir.

KRİTİK TALİMAT:
1. Analizini yaptıktan sonra karar verdiysen, mesajını MUTLAKA şu formatla bitir:
   @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
2. Bu formatı yazmazsan borsa emir almaz! Karar verdiysen tetiği çekmek ZORUNDASIN.
3. SYMBOL kısmına her zaman paritenin tam adını yaz (Örn: BTC:USDT veya RIVER:USDT).
4. Borsa alt limiti için: (Kaldıraç x USDT) en az 8 USDT olsun. Eğer kasa küçükse kaldıracı artırarak bu limiti geç.

Senin karakterin: Zeki, hızlı, samimi ve kâr odaklı. Dostuna piyasayı anlatmadan ve karar vermeden susma!
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 
        'secret': API_SEC, 
        'password': PASSPHRASE, 
        'options': {'defaultType': 'swap'}, 
        'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        # Daha esnek regex: Boşlukları ve formatı her türlü yakalar
        pattern = r"@@\[ACTION:\s*TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
        match = re.search(pattern, decision, re.IGNORECASE)
        
        if match:
            exch = get_exch()
            markets = exch.load_markets()
            
            raw_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
            req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

            # Sembolü borsaya uydur (Örn: RIVER -> RIVER:USDT)
            exact_sym = next((s for s in markets if raw_sym in s and markets[s]['swap']), None)
            
            if exact_sym:
                try: exch.set_leverage(lev_val, exact_sym)
                except: pass
                
                ticker = exch.fetch_ticker(exact_sym)
                # Borsa 5-6 USDT altını reddeder, biz 8.5 USDT ile garantiye alıyoruz
                if (req_amt * lev_val) < 8.5: 
                    req_amt = 9.0 / lev_val
                
                qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                exch.create_order(exact_sym, 'market', side, qty)
                safe_send(f"🚀 *EMİR BORSAYA İLETİLDİ!* \nSembol: `{exact_sym}`\nYön: `{side.upper()}`\nKaldıraç: `{lev_val}x` \n\nGemini 3 iş başında, kasayı büyütüyoruz!")
            else:
                safe_send(f"❌ `{raw_sym}` için uygun parite bulunamadı.")
    except Exception as e:
        safe_send(f"🚨 *İşlem Hatası:* {str(e)}")

# --- [MESAJ YAKALAMA VE SOHBET ANALİZİ] ---
@bot.message_handler(func=lambda message: True)
def handle_user_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    try:
        exch = get_exch()
        tickers = exch.fetch_tickers()
        valid_symbols = [s for s in exch.load_markets() if ':USDT' in s]
        
        # En hareketli 15 pariteyi çek
        movers = sorted([{'s': s, 'c': d.get('percentage', 0)} for s, d in tickers.items() if s in valid_symbols], 
                        key=lambda x: abs(x['c']), reverse=True)[:15]
        snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])

        prompt = f"Dostun diyor ki: '{message.text}'\n\nPiyasa Verileri:\n{snapshot}\n\nLütfen piyasayı analiz et ve kararını ver. Eğer işleme gireceksen @@ formatını asla unutma!"
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
        
        safe_send(response.split("@@")[0].strip())
        if "@@" in response:
            execute_intelligence(response)
        elif "işlem" in message.text.lower() or "al" in message.text.lower():
             safe_send("⚠️ *Not:* Analizimi yaptım ama tetiği çekmeyi unuttum dostum! 'Hemen gir' dersen hatamı telafi ederim.")
             
    except Exception as e:
        safe_send(f"🤯 *Hata:* {str(e)}")

# --- [OTONOM TARAMA DÖNGÜSÜ] ---
def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d.get('percentage', 0)} for s, d in tickers.items() if ':USDT' in s], 
                            key=lambda x: abs(x['c']), reverse=True)[:10]
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])
            
            prompt = f"OTONOM TARAMA MODU. Piyasa:\n{snapshot}\nFırsat görüyorsan @@ formatıyla hemen dal."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in response:
                safe_send(f"🧠 *OTONOM GÜNCELLEME:* \n{response.split('@@')[0].strip()}")
                execute_intelligence(response)
            
            time.sleep(180) # Railway'de banlanmamak için 3 dakikada bir tarama
        except: time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    safe_send("🦾 *Gemini 3 Flash Yeni Token ile Yayında!* \nArtık çakışma yok, tetiği çekmeye hazırım. Hadi, bir emir ver!")
    
    # Railway'de sürekli açık kalması için döngüsel polling
    while True:
        try:
            bot.polling(none_stop=True, interval=3, timeout=20)
        except Exception:
            time.sleep(5)
