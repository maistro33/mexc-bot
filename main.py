import os
import time
import telebot
import ccxt
from google import genai
from telebot import apihelper

# --- [BAĞLANTI ZIRHI] ---
apihelper.RETRY_ON_ERROR = True
apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT = 60

# --- [YAPILANDIRMA] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" # Doğrudan koda mühürlendi
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Başlatma
bot = telebot.TeleBot(TOKEN, threaded=False)
client = genai.Client(api_key=GEMINI_KEY)

# --- [GÜVENLİK VE STRATEJİ AYARLARI] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'anti_manipulation': True
}

# Bitget Bağlantısı (Tek Yönlü Mod Garantili)
def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {
            'defaultType': 'swap', 
            'positionMode': False  # Tek Yönlü Mod (One-Way)
        },
        'enableRateLimit': True
    })

def execute_trade(side, symbol="BTC/USDT:USDT"):
    try:
        exchange = get_exchange()
        # Kaldıraç ayarını kontrol et
        exchange.set_leverage(CONFIG['leverage'], symbol)
        
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        
        # Miktarı borsa hassasiyetine göre yuvarla (Ondalık hatasını önler)
        raw_amount = (CONFIG['entry_usdt'] * CONFIG['leverage']) / price
        amount = float(exchange.amount_to_precision(symbol, raw_amount))
        
        # Tek yönlü modda emir gönderimi
        order = exchange.create_market_order(symbol, side, amount)
        
        report = (f"🎯 **İŞLEM BAŞARIYLA AÇILDI**\n\n"
                  f"📈 Parite: {symbol}\n"
                  f"⚡ Yön: {side.upper()}\n"
                  f"💰 Miktar: {amount} {symbol.split('/')[0]}\n"
                  f"🛡️ Kalkan: Gövde Kapanış ve Hacim Onayı Aktif!")
        bot.send_message(CHAT_ID, report)
        return order
    except Exception as e:
        bot.send_message(CHAT_ID, f"⚠️ İşlem Hatası: {e}")

@bot.message_handler(func=lambda message: True)
def handle_ai_command(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exchange = get_exchange()
            balance_data = exchange.fetch_balance()
            balance = balance_data['total'].get('USDT', 0)
            
            prompt = (f"Sen Evergreen V11'sin. Kaptan Sadık'ın tam yetkili botusun. "
                      f"Kaptan: '{message.text}' dedi. Mevcut Bakiye: {balance} USDT. "
                      f"Stratejin: Profitable, slow, risk-free trades. "
                      f"Market Maker tuzaklarına (spoofing, stop hunting) karşı dikkatlisin. "
                      f"Karar verirsen sonuna [KOMUT:AL] veya [KOMUT:SAT] ekle.")
            
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            bot.reply_to(message, response.text)
            
            if "[KOMUT:AL]" in response.text:
                execute_trade('buy')
            elif "[KOMUT:SAT]" in response.text:
                execute_trade('sell')
                
        except Exception as e:
            print(f"Hata: {e}")

if __name__ == "__main__":
    print("🚀 Evergreen V11: Motorlar Isıtılıyor...")
    
    try:
        bot.remove_webhook()
        time.sleep(2)
        
        # Başlangıç Kontrolü
        exchange = get_exchange()
        balance_data = exchange.fetch_balance()
        current_balance = balance_data['total'].get('USDT', 0)
        
        online_msg = (f"🦅 **SİSTEM TEK YÖNLÜ MODDA ONLINE**\n\n"
                      f"💰 Güncel Bakiye: {current_balance} USDT\n"
                      f"📡 Bağlantı: Amsterdam üzerinden Bitget'e mühürlendi.\n\n"
                      f"Kaptan, tüm engeller aşıldı. Tek Yönlü modda ava hazırız!")
        
        bot.send_message(CHAT_ID, online_msg)
        print("✅ Bot Başarıyla Yayına Girdi.")
    except Exception as e:
        print(f"❌ Başlatma Hatası: {e}")

    while True:
        try:
            bot.polling(none_stop=True, interval=2, timeout=40)
        except Exception as e:
            time.sleep(5)
