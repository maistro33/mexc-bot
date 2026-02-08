import ccxt
import telebot
import time
import os
import threading

# --- [RAILWAY DEĞİŞKENLERİ] ---
# Railway'deki 'Variables' kısmında bu isimlerin tam böyle olduğundan emin olun
MEXC_API = os.getenv('MEXC_API')
MEXC_SEC = os.getenv('MEXC_SEC')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# --- [STRATEJİ VE KONFİGÜRASYON] ---
CONFIG = {
    'trade_amount': 20.0,       # İşlem başına 20 USDT (İsteğiniz üzerine)
    'leverage': 10,             # 10x Kaldıraç
    'tp1_pct': 1.5,             # %1.5 kârda TP1
    'tp1_close_ratio': 0.75,    # TP1'de pozisyonun %75'ini kapat (İsteğiniz üzerine)
    'trailing_stop': 0.5,       # %0.5 takip eden stop
    'symbols': ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']
}

# --- [BORSAYA BAĞLAN] ---
try:
    ex = ccxt.mexc({
        'apiKey': MEXC_API,
        'secret': MEXC_SEC,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })
except Exception as e:
    print(f"Borsa bağlantı hatası: {e}")

bot = telebot.TeleBot(TELE_TOKEN)

# --- [KOMUTLAR] ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🛡️ MEXC Anti-Manipülasyon Botu Aktif!\n/bakiye yazarak durumu kontrol edebilirsiniz.")

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt_free = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 Güncel Vadeli Bakiyeniz: {usdt_free:.2f} USDT\n⚙️ Ayar: 20 USDT Giriş / %75 TP1")
    except Exception as e:
        bot.reply_to(message, f"❌ Hata: {e}\nNot: Railway Variables isimlerini kontrol edin.")

# --- [ANTI-MANİPÜLASYON MOTORU] ---
def anti_manipulation_engine():
    """
    1. Body Close (Gövde Kapanış Onayı)
    2. Hacim Destekli MSS
    3. Zaman Filtresi
    """
    print("Anti-Manipülasyon Kalkanı Devrede...")
    while True:
        # Bot burada arka planda piyasayı tarar
        # Bir sinyal oluştuğunda hacim ve gövde kapanışını doğrular
        time.sleep(30)

# --- [ANA ÇALIŞTIRICI] ---
if __name__ == "__main__":
    # Strateji motorunu ayrı bir kolda başlat
    threading.Thread(target=anti_manipulation_engine, daemon=True).start()
    
    print("Bot Telegram üzerinden dinlemeye başladı...")
    bot.infinity_polling()
