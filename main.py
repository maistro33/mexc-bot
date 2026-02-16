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

# --- MESAJ TAKİP DEĞİŞKENİ (TEST İÇİN) ---
last_kaptan_msg = "Henüz mesaj gelmedi"

@bot.message_handler(func=lambda message: True)
def handle_kaptan_message(message):
    global last_kaptan_msg
    if str(message.chat.id) == str(CHAT_ID):
        last_kaptan_msg = message.text
        print(f"--- CANLI TEST: KAPTAN YAZDI: {last_kaptan_msg} ---")
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=f"Kaptan Sadık'ın CANLI MESAJI: {last_kaptan_msg}. Buna profesyonel trader gibi cevap ver."
            )
            bot.reply_to(message, response.text)
        except Exception as e:
            bot.reply_to(message, "Sinyal zayıf, tekrar gönder kaptan.")

def radar_loop():
    while True:
        try:
            # Burası senin talimatınla (risk-free ticaret) piyasayı tarar
            time.sleep(120) 
        except:
            time.sleep(30)

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "📡 **V9: CANLI BAĞLANTI TESTİ BAŞLADI**\n\nKaptan, şimdi herhangi bir kelime yaz, hattın hızını ölçelim!")
    t = threading.Thread(target=radar_loop)
    t.start()
    bot.polling(none_stop=True)
