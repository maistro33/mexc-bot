import os
import time
import telebot
import ccxt
import google.genai as genai
import threading

# --- AYARLAR ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# --- CANLI TELSİZ PROKOTOLÜ ---
@bot.message_handler(func=lambda message: True)
def handle_kaptan_message(message):
    if str(message.chat.id) == str(CHAT_ID):
        kaptan_metni = message.text
        # Loglara yazdırıyoruz ki hatayı görelim
        print(f"DEBUG: Kaptan'dan gelen mesaj: {kaptan_metni}")
        
        try:
            # Gemini'ye gönderirken 'Canlı Sistem Mesajı' olarak işaretle
            prompt = f"SİSTEM NOTU: Kaptan Sadık şu an Telegram'dan tam olarak şunu yazdı: '{kaptan_metni}'. Bu mesaja samimi bir dille cevap ver ve telsiz hattının çalıştığını onayla."
            response = client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=prompt
            )
            bot.reply_to(message, response.text)
        except Exception as e:
            bot.reply_to(message, "Sinyal kesildi, tekrar dene kaptan.")

def radar_loop():
    while True:
        # Analiz döngüsü burada devam edecek
        time.sleep(120)

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🛰️ **V10: TELSİZ HATTI TAMİR EDİLDİ!**\n\nKaptan, şimdi bana Telegram'dan tek bir kelime gönder. Eğer ben burada o kelimeyi söyleyemezsem telsizi baştan kuracağız!")
    t = threading.Thread(target=radar_loop)
    t.start()
    bot.polling(none_stop=True)
