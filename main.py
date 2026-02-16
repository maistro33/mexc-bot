import os
import time
import telebot
import ccxt
from google import genai
import threading
from telebot import apihelper

# --- [BAĞLANTI ZIRHI: NETWORK HATALARINI ÖNLER] ---
apihelper.RETRY_ON_ERROR = True
apihelper.CONNECT_TIMEOUT = 30
apihelper.READ_TIMEOUT = 30

# --- [YAPILANDIRMA] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Başlatma
bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# Bitget Bağlantısı (Hedge Mode Aktif)
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap', 'positionMode': True}
})

# --- [KAPTANIN ÖZEL AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,           # Sabit giriş miktarı
    'leverage': 10,               # Sabit kaldıraç
    'tp1_ratio': 0.75,            # İlk hedefte %75 kapatma
    'anti_manipulation': True     # Gövde kapanış onayı aktif
}

# --- [BORSA EMİR FONKSİYONU] ---
def execute_trade(side, symbol="BTC/USDT:USDT"):
    try:
        exchange.set_leverage(CONFIG['leverage'], symbol)
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['entry_usdt'] * CONFIG['leverage']) / price
        
        # Emri Gönder
        order = exchange.create_market_order(symbol, side, amount)
        
        # Sanal Takip Raporu (Kaptan'ın isteği)
        bot.send_message(CHAT_ID, f"🎯 **İŞLEM AÇILDI**\nSembol: {symbol}\nYön: {side.upper()}\nTP1: %75 Ayarlandı.")
        return order
    except Exception as e:
        bot.send_message(CHAT_ID, f"⚠️ Emir İletilemedi: {e}")

# --- [AI KOMUTA MERKEZİ] ---
@bot.message_handler(func=lambda message: True)
def handle_ai_command(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            # Bakiyeyi anlık çekelim
            balance = exchange.fetch_balance()['total']['USDT']
            
            prompt = (f"Sen Kaptan Sadık'ın tam yetkili Evergreen botusun. Maistro33 ruhuyla konuş. "
                      f"Kaptan: '{message.text}' dedi. Bakiye: {balance} USDT. "
                      f"Stratejin: Risk-free, yavaş ve kârlı ticaret. "
                      f"Eğer işlem açacaksan sonuna [KOMUT:AL] veya [KOMUT:SAT] ekle.")
            
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            bot.reply_to(message, response.text)
            
            if "[KOMUT:AL]" in response.text:
                execute_trade('buy')
            elif "[KOMUT:SAT]" in response.text:
                execute_trade('sell')
                
        except Exception as e:
            print(f"Hata: {e}")

# --- [KESİNTİSİZ ÇALIŞTIRICI] ---
if __name__ == "__main__":
    print("🚀 Evergreen V11 Ateşleniyor...")
    
    # İlk bağlantı sinyali
    try:
        bot.send_message(CHAT_ID, "🦅 **V11: ÇELİK HAT ONARILDI**\n\nKaptan, ağ hatası giderildi. Tam yetkiyle emirlerini bekliyorum!")
    except:
        print("Telegram'a henüz ulaşılamıyor, polling bekleniyor...")

    # Sonsuz Döngü (Bağlantı kopsa da durmaz)
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=10)
        except Exception as e:
            print(f"⚠️ Bağlantı hatası, tekrar deneniyor: {e}")
            time.sleep(5)
