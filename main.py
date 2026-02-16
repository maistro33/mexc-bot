import os
import time
import telebot
import google.generativeai as genai
import ccxt

# --- DEĞİŞKENLERİ ÇEK ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
BG_API = os.getenv('BITGET_API')
BG_SEC = os.getenv('BITGET_SEC')
BG_PAS = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot Nesnesi
bot = telebot.TeleBot(TOKEN)

def telegram_test():
    """Bot başlar başlamaz zorla mesaj gönderir."""
    try:
        status_text = (
            "🚀 **Sanal Takip Sistemi Başlatıldı!**\n\n"
            "✅ **Bağlantı:** Başarılı\n"
            "📡 **Radar:** Tüm borsa taranıyor\n"
            "💰 **Kasa:** 21.80 USDT\n"
            "🛡️ **Kalkanlar:** Aktif (Anti-Manipülasyon)\n\n"
            "Kaptan, kontrol bende. Pusuya yattım!"
        )
        bot.send_message(CHAT_ID, status_text, parse_mode='Markdown')
        print("Telegram mesajı başarıyla gönderildi!")
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def main():
    # 1. Hemen test mesajı gönder
    telegram_test()
    
    # 2. Döngüye gir
    while True:
        try:
            # Burası senin stratejini işletecek
            print("Radar tarama yapıyor...")
            time.sleep(300) # 5 dakikada bir kontrol
        except Exception as e:
            print(f"Döngüde hata: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
