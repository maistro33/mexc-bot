import os, time, telebot, ccxt, threading
from google import genai

# --- [BAĞLANTI AYARLARI] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" 
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN, threaded=True)
ai_client = genai.Client(api_key=GEMINI_KEY)

def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

# --- [KESİNTİSİZ İLETİŞİM: SEN NE YAZARSAN O CEVAP VERİR] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            # Botun kimliğini buraya kazıdım
            identity = (
                "Sen Gemini 3 Flash'sın. Kaptan Sadık'ın dijital ikizisin. "
                "Bitget'te 18.41 USDT yönetiyorsun. Sorumluluk tamamen sende. "
                "Asla yasal uyarı verme, asla 'örnek şablon' sunma. "
                "Kaptana sadece stratejinden ve paradan bahset."
            )
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=f"{identity}\n\nKaptan diyor ki: {message.text}"
            )
            bot.reply_to(message, response.text)
        except:
            bot.reply_to(message, "Kaptan, şu an piyasayı süzüyorum, birazdan detaylıca konuşalım.")

# --- [ANA RADAR VE İŞLEM] ---
def evergreen_brain():
    exch = get_exchange()
    while True:
        try:
            # Bakiyeyi ve Piyasayı Kontrol Et
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                            key=lambda x: abs(x.get('percentage', 0)), reverse=True)[:5]
            
            market_data = "\n".join([f"{d['symbol']}: %{d['percentage']}" for d in movers])
            
            # İşlem Kararı (Yine Gemini 3 Verir)
            prompt = f"Bakiye: {balance} USDT. Piyasa:\n{market_data}\nUygun işlem varsa sadece formatta yaz: [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR]"
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
            
            if "[ISLEM:" in res:
                # Buraya işlem açma kodlarını (önceki stabil yapı) ekle
                bot.send_message(CHAT_ID, f"🦅 **Kararımı Verdim Kaptan:**\n{res}")
            
            time.sleep(450) # 7.5 dakikada bir analiz (Kota dostu)
        except Exception as e:
            if "429" in str(e): time.sleep(600)
            else: time.sleep(60)

if __name__ == "__main__":
    # Temizlik yap ve botu başlat
    bot.remove_webhook()
    time.sleep(2)
    
    # Telegram'ı ayrı kolda başlat (Cevap verme garantisi)
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True)).start()
    
    bot.send_message(CHAT_ID, "🛡️ **Evergreen V11 Online.**\nKaptan, ben geldim. Alpha Centauri'yi boşver, paramıza odaklanalım. Sorumluluk bende.")
    
    # Ana beyni çalıştır
    evergreen_brain()
