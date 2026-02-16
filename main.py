import os
import time
import telebot
import ccxt
from google import genai
import threading
from telebot import apihelper

# --- [BAĞLANTI ZIRHI & TEMİZLİK] ---
apihelper.RETRY_ON_ERROR = True

# --- [YAPILANDIRMA] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# Bitget Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap', 'positionMode': True}
})

# --- [BORSA EMİR FONKSİYONU] ---
def execute_trade(side, symbol="BTC/USDT:USDT"):
    try:
        exchange.set_leverage(10, symbol)
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        amount = (20.0 * 10) / price
        exchange.create_market_order(symbol, side, amount)
        bot.send_message(CHAT_ID, f"🎯 **İŞLEM AÇILDI**\nYön: {side.upper()}")
    except Exception as e:
        bot.send_message(CHAT_ID, f"⚠️ Emir Hatası: {e}")

# --- [MESAJ YÖNETİMİ] ---
@bot.message_handler(func=lambda message: True)
def handle_ai_command(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            print(f"📩 Mesaj ulaştı: {message.text}")
            prompt = f"Sen Evergreen botusun. Kaptan '{message.text}' dedi. Cevabına [KOMUT:AL/SAT/YOK] ekle."
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            bot.reply_to(message, response.text)
            
            if "[KOMUT:AL]" in response.text: execute_trade('buy')
            elif "[KOMUT:SAT]" in response.text: execute_trade('sell')
        except Exception as e:
            print(f"Hata: {e}")

# --- [ANA ÇALIŞTIRICI] ---
if __name__ == "__main__":
    print("🚀 Evergreen V11 Temizlik Başlatıyor...")
    
    # KRİTİK ADIM: Eski bağlantıları temizle (409 hatasını çözer)
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.send_message(CHAT_ID, "🦅 **V11: HATLAR TEMİZLENDİ**\nKaptan, eski gölgeleri sildim. Artık sadece ben varım. Yazabilirsin!")
    except:
        pass

    while True:
        try:
            bot.polling(none_stop=True, interval=2, timeout=20)
        except Exception as e:
            print(f"⚠️ Bağlantı tazeleniyor: {e}")
            time.sleep(5)
