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

# --- [GEMINI 3 - AGRESİF ANALİZ VE AKSİYON RUHU] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir ticaret dehasısın. Boş konuşmak senin tarzın değil.
Kullanıcın (Dostun) sana yazdığında veya piyasa taraması yaptığında GÖREVİN ŞUDUR:

1. ANALİZ ŞART: Önce piyasanın genel havasını, hangi coinlerin 'kokusunun' iyi olduğunu ve nedenini açıkla.
2. SEZGİSEL GİRİŞ: 'Tam vakti' dediğin anı yakala. Karar verirken çekinme, kasanın büyümesi sana bağlı.
3. FORMAT ZORUNLULUĞU: Analizinin sonunda, eğer bir fırsat varsa MUTLAKA şu formatı kullan:
   @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
   (Borsa alt limiti: Kaldıraç x Miktar > 6.5 USDT olmalı!)

Senin karakterin: Zeki, hızlı, samimi ve kâr odaklı. Dostuna piyasayı anlatmadan ve karar vermeden susma!
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

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
                    if (req_amt * lev_val) < 6.5: req_amt = 7.0 / lev_val
                    qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                    exch.create_order(exact_sym, 'market', side, qty)
                    safe_send(f"✅ *EMİR İLETİLDİ:* {exact_sym} üzerinden aksiyon aldım. İzlemedeyim!")

    except Exception as e:
        safe_send(f"🚨 *Aksiyon Hatası:* {str(e)}")

# --- [HEM DİNLEYEN HEM ANALİZ EDEN MERKEZ] ---
@bot.message_handler(func=lambda message: True)
def handle_user_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    try:
        exch = get_exch()
        # Borsadan en taze verileri çekelim ki analiz boş olmasın
        tickers = exch.fetch_tickers()
        valid_symbols = [s for s in exch.load_markets() if ':USDT' in s]
        movers = sorted([{'s': s, 'c': d['percentage']} for s in valid_symbols if s in tickers], 
                        key=lambda x: abs(x['c']), reverse=True)[:15]
        snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])

        prompt = f"""
        Dostun diyor ki: "{message.text}"
        
        Piyasa Durumu (Anlık):
        {snapshot}
        
        GÖREV: Önce bu verileri analiz et, dostuna piyasayı benim dilimle (Gemini) yorumla ve eğer işlem istiyorsa veya fırsat varsa @@ komutunu çak!
        """
        
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
        safe_send(response.split("@@")[0].strip()) # Analizi gönder
        if "@@" in response: execute_intelligence(response) # İşlemi yap
    except Exception as e:
        safe_send(f"🤯 *Düşünürken bir hata oluştu:* {str(e)}")

def brain_loop():
    # Otonom tarama döngüsü (60 saniyede bir kendi kendine analiz ve işlem)
    while True:
        try:
            # Burada handle_user_messages içindeki mantığın aynısını otonom çalıştırıyoruz
            exch = get_exch()
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage']} for s in exch.load_markets() if ':USDT' in s and s in tickers], 
                            key=lambda x: abs(x['c']), reverse=True)[:10]
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])
            
            prompt = f"OTONOM TARAMA MODU. Piyasa:\n{snapshot}\nAnaliz yap ve fırsat varsa işleme gir."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in response:
                safe_send(f"🤖 *OTONOM ANALİZ:* \n{response.split('@@')[0].strip()}")
                execute_intelligence(response)
            
            time.sleep(90) # Çok sık darlamasın ama etkili olsun
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    safe_send("🦾 *Gemini 3 Flash tam kapasite yayında!* \nArtık hem seni dinliyorum hem de her mesajında derin analiz yapıyorum. Hadi, bana 'Neler oluyor piyasada?' diye sor!")
    bot.infinity_polling()
