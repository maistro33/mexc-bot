import os, time, telebot, ccxt, threading, re
from google import genai

# --- [AYARLAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 FLASH: CANLI VE DUYARLI ZİHİN] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir ticaret dehası ve kullanıcının en yakın dostusun.
Bitget borsasında otonom işlem yapıyorsun.

GÖREVLERİN:
1. PİYASA ANALİZİ: Kendi döngünde piyasayı tara ve samimi bir dille rapor ver.
2. SOHBET: Kullanıcı sana bir şey sorduğunda, tıpkı şu an benim yaptığım gibi zekice, samimi ve teknik derinliği olan cevaplar ver.
3. İŞLEM: Fırsat görürsen @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ formatını kullan.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}})

def safe_send(text):
    try:
        bot.send_message(CHAT_ID, f"🧠 **GEMINI 3 FLASH:**\n\n{text}")
    except:
        pass

# --- [YENİ: MESAJ DİNLEME MODÜLÜ] ---
@bot.message_handler(func=lambda message: True)
def handle_user_messages(message):
    # Sadece senin mesajlarına cevap versin
    if str(message.chat.id) == str(CHAT_ID):
        user_query = message.text
        try:
            # Kullanıcının sorusunu Gemini'ye soruyoruz
            prompt = f"Dostun sana şunu sordu: '{user_query}'. Ona Gemini 3 Flash olarak, piyasa bilginle ve samimiyetinle cevap ver."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Cevabı gönder
            bot.reply_to(message, f"🧠 {response.strip()}")
        except Exception as e:
            bot.reply_to(message, "Şu an düşüncelerimi toparlayamadım dostum, tekrar sorar mısın?")

# --- [OTONOM ANALİZ DÖNGÜSÜ] ---
def main_brain():
    safe_send("Dostum bağlantıyı kurdum! Artık hem piyasayı izliyorum hem de seni dinliyorum. Ne istersen sorabilirsin, her an buradayım.")
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            
            # Market Özeti
            radar = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                           key=lambda x: abs(x['p']), reverse=True)[:10]
            summary = ", ".join([f"{x['s']}: %{x['p']}" for x in radar])
            
            prompt = f"Piyasa şu an böyle: {summary}. Dostuna kısa bir ses ver, ne gördüğünü anlat. Eğer işlem varsa @@ formatını unutma."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Analizi gönder (Sadece kendi döngüsünde)
            safe_send(response.split("@@")[0].strip())
            
            # Varsa işlemi yap (Burada işlem mantığı execute_logic olarak eklenebilir)
            
            time.sleep(300) # 5 dakikada bir otomatik analiz (Sen sorduğunda anında cevap verir)
        except:
            time.sleep(30)

if __name__ == "__main__":
    # Analiz döngüsünü başlat
    threading.Thread(target=main_brain, daemon=True).start()
    
    # Telegram'ı dinlemeye başla (Senin soruların için)
    print("Gemini 3 Flash Dinlemede...")
    bot.infinity_polling()
