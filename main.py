import os, time, telebot, ccxt, threading
from google import genai

# --- [BAĞLANTI AYARLARI] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot Nesnesi (Cevap verme garantili ayarlar)
bot = telebot.TeleBot(TOKEN, threaded=True)
ai_client = genai.Client(api_key=GEMINI_KEY)

def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

# --- [SENİNLE KONUŞAN ZEKA] ---
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """Sen ne yazarsan yaz, Gemini 3 gibi anında cevap verir."""
    if str(message.chat.id) == str(CHAT_ID):
        try:
            prompt = f"Sen Evergreen V11'sin (Gemini 3). Kaptan Sadık şunu sordu: {message.text}. Kaptanına samimi ve zeki bir cevap ver."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            bot.reply_to(message, response.text)
        except Exception as e:
            if "429" in str(e):
                bot.reply_to(message, "Kaptan, çok konuştuk kota doldu! 5 dk dinlenip geliyorum.")
            else:
                bot.reply_to(message, "Buradayım Kaptan, piyasayı süzüyorum.")

# --- [OTONOM RADAR VE İŞLEM] ---
def evergreen_brain():
    exch = get_exchange()
    while True:
        try:
            # Analiz ve İşlem Mantığı (Kota dostu: 10 dakikada bir)
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], key=lambda x: abs(x.get('percentage', 0)), reverse=True)[:5]
            
            market_data = "\n".join([f"{d['symbol']}: %{d['percentage']}" for d in movers])
            prompt = f"Bakiye: {balance}. Piyasa:\n{market_data}\nİşlem kararı ver: [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR] veya [PAS]"
            
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
            
            if "[ISLEM:" in res:
                # İşlem kodları buraya (Önceki stabil yapı)
                bot.send_message(CHAT_ID, f"🚀 **İşleme Karar Verdim:**\n{res}")
            
            time.sleep(600) # 10 dakika bekle (Kota koruması)
        except:
            time.sleep(60)

# --- [ANA ÇALIŞTIRICI: TEMİZ SAYFA] ---
if __name__ == "__main__":
    # 1. Eski bağlantıları zorla kopar (409 hatasını bitirir)
    bot.remove_webhook()
    time.sleep(3)
    
    # 2. Telegram'ı ayrı bir kolda (Thread) başlat (Cevap verme garantisi)
    tele_thread = threading.Thread(target=lambda: bot.infinity_polling(timeout=90, skip_pending=True))
    tele_thread.daemon = True
    tele_thread.start()
    
    bot.send_message(CHAT_ID, "🛡️ **Kaptan, Evergreen V11 (Gemini 3) bağlandı!**\nArtık sesini duyuyorum. Sorumluluk bende, bakiye sende. Ne yapalım?")
    
    # 3. Beyni başlat
    evergreen_brain()
