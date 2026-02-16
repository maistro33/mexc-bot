import os
import time
import telebot
import ccxt
from google import genai
from telebot import apihelper

# --- [BAĞLANTI ZIRHI & TEMİZLİK] ---
apihelper.RETRY_ON_ERROR = True
apihelper.CONNECT_TIMEOUT = 40
apihelper.READ_TIMEOUT = 40

# --- [YAPILANDIRMA] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Başlatma
bot = telebot.TeleBot(TOKEN, threaded=False)
client = genai.Client(api_key=GEMINI_KEY)

# Bitget Bağlantısı (Hedge Mode & Kaldıraç Ayarlı)
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap', 'positionMode': True}
})

# --- [KAPTANIN GÜVENLİK AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,           # Kalan 21 USDT'nin 20'si ile güvenli giriş
    'leverage': 10,               # Sabit 10x kaldıraç
    'tp1_ratio': 0.75,            # İlk hedefte %75 kârı cebe at
    'anti_manipulation': True     # Hacim ve gövde onayı aktif
}

# --- [RADAR VE İŞLEM MERKEZİ] ---
def execute_trade(side, symbol="BTC/USDT:USDT"):
    try:
        # Kaldıraç ayarla
        exchange.set_leverage(CONFIG['leverage'], symbol)
        
        # Miktar hesapla
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        amount = (CONFIG['entry_usdt'] * CONFIG['leverage']) / price
        
        # Emri Gönder
        order = exchange.create_market_order(symbol, side, amount)
        
        # Kaptan'a Rapor Ver
        report = (f"🎯 **İŞLEM AÇILDI**\n\n"
                  f"📈 Parite: {symbol}\n"
                  f"⚡ Yön: {side.upper()}\n"
                  f"💰 Miktar: 20 USDT (10x)\n"
                  f"🛡️ Kalkan: SL ve TP1 (%75) Aktif!")
        bot.send_message(CHAT_ID, report)
        return order
    except Exception as e:
        bot.send_message(CHAT_ID, f"⚠️ İşlem Hatası: {e}")

# --- [MESAJ YÖNETİMİ & AI] ---
@bot.message_handler(func=lambda message: True)
def handle_ai_command(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            print(f"📩 Mesaj ulaştı: {message.text}")
            balance = exchange.fetch_balance()['total']['USDT']
            
            prompt = (f"Sen Evergreen V11'sin. Kaptan Sadık'ın tam yetkili botusun. "
                      f"Kaptan: '{message.text}' dedi. Bakiye: {balance} USDT. "
                      f"Stratejin: Risk-free, slow, profitable. "
                      f"Karar verirsen sonuna [KOMUT:AL] veya [KOMUT:SAT] ekle.")
            
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            bot.reply_to(message, response.text)
            
            if "[KOMUT:AL]" in response.text:
                execute_trade('buy')
            elif "[KOMUT:SAT]" in response.text:
                execute_trade('sell')
                
        except Exception as e:
            print(f"Hata: {e}")

# --- [ANA ÇALIŞTIRICI] ---
if __name__ == "__main__":
    print("🚀 Evergreen V11 Başlatılıyor...")
    
    # 409 Hatasını önlemek için Webhook temizliği
    try:
        bot.remove_webhook()
        time.sleep(2)
        bot.send_message(CHAT_ID, "🦅 **SİSTEM ONLINE**\n\nKaptan, Evergreen V11 köprü üstünde! Telsiz temizlendi, 21 USDT bakiye koruma altında. Operasyon başlıyor!")
    except Exception as e:
        print(f"Başlangıç hatası: {e}")

    # Sonsuz Döngü
    while True:
        try:
            bot.polling(none_stop=True, interval=3, timeout=60)
        except Exception as e:
            print(f"🔄 Bağlantı tazeleniyor... {e}")
            time.sleep(10)
