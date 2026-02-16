import os
import time
import telebot
import ccxt
import google.genai as genai
import warnings

# Gereksiz kütüphane uyarılarını temizle
warnings.filterwarnings("ignore")

# --- 1. AYARLAR VE KİMLİK (Environment Variables) ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Başlatma
bot = telebot.TeleBot(TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# Borsa Bağlantısı (Bitget)
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

def send_telegram(message):
    """Kaptana Telegram üzerinden rapor verir."""
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

# --- 2. ANA STRATEJİ VE OPERASYON ---
if __name__ == "__main__":
    # Bot açılış selamı
    send_telegram("🚀 **EVERGREEN SİSTEMİ BAŞLATILDI**\nBakiye ve Radarlar kontrol ediliyor...")

    while True:
        try:
            # A) CANLI TELSİZ MESAJI (Gemini'den komut al)
            # Kota dostu olması için 120 saniyede bir çalışır
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents="Kaptan evergreen'e kısa bir selamlama yap, 'Hattayım kaptan, evergreen burda' cümlesini mutlaka kullan."
                )
                if response.text:
                    send_telegram(f"📡 **CANLI KOMUT:**\n\n{response.text}")
            except Exception as ai_err:
                if "429" in str(ai_err):
                    print("Kota doldu, AI bu turu pas geçiyor.")
                else:
                    print(f"AI Hatası: {ai_err}")

            # B) BAKİYE VE RADAR KONTROLÜ
            # Cüzdan kontrolü
            balance = exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            
            # Pazar taraması (Sanal Takip)
            tickers = exchange.fetch_tickers()
            # Sadece USDT çiftlerini ve hacimli olanları al
            pairs = [s for s in tickers if '/USDT:USDT' in s]
            top_pairs = sorted(pairs, key=lambda x: tickers[x].get('quoteVolume', 0), reverse=True)[:5]

            for symbol in top_pairs:
                change = tickers[symbol].get('percentage', 0)
                # %3 ve üzeri hareketleri raporla
                if abs(change) > 3:
                    send_telegram(f"🔍 **[RADAR]** {symbol}\n📈 Değişim: %{change:.2f}\n🛡️ Durum: Sanal Takipte.")

            # C) PERİYODİK DURUM RAPORU
            print(f"Bakiye: {usdt_balance} USDT | Döngü başarılı.")
            
            # Kota ve istikrar için 2 dakikalık (120 sn) derin uyku
            time.sleep(120)

        except Exception as e:
            print(f"Ana Döngü Hatası: {e}")
            time.sleep(15)
