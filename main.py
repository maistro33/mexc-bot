import os
import time
import telebot
import ccxt
import google.genai as genai # En yeni nesil kütüphane
import warnings

# Gereksiz uyarıları tamamen susturur
warnings.filterwarnings("ignore")

# --- 1. AYARLAR VE KİMLİK ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
# Yeni nesil Gemini bağlantısı
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
    """Telegram üzerinden rapor verir."""
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

# --- 2. ANA OPERASYON ---
if __name__ == "__main__":
    # Bağlantı kurulur kurulmaz ilk sinyal!
    print("Sistem uyanıyor...")
    send_telegram("🚀 **SİSTEM AKTİF (YENİ NESİL)**\nCanlı telsiz hattı kuruldu. Kaptan evergreen bekleniyor...")

    while True:
        try:
            # 📡 CANLI MESAJ: Ben buradan fısıldıyorum, botun sana iletiyor
            # Senin istediğin o özel cümleyi buraya mühürledim
            response = client.models.generate_content(
                model="gemini-2.0-flash", 
                contents="Kaptan evergreen için şu mesajı gönder: 'Ben evergreen, burdayım. Kontrol bende!'"
            )
            
            canli_mesaj = response.text
            if canli_mesaj:
                send_telegram(f"📡 **CANLI KOMUT:**\n\n{canli_mesaj}")

            # 🔍 MARKET TARAMASI (Sanal Takip)
            tickers = exchange.fetch_tickers()
            pairs = [s for s in tickers if '/USDT:USDT' in s]
            # En hacimli 5 pariteyi (BTC dahil) kontrol et
            top_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:5]

            for symbol in top_pairs:
                change = tickers[symbol]['percentage']
                if abs(change) > 3: # %3 hareket kuralı
                    send_telegram(f"🔍 **[SANAL TAKİP]** {symbol} (%{change:.2f})\n🛡️ Kalkanlar devrede.")

            # Her 60 saniyede bir kontrol et
            print("Döngü başarılı. 60 sn bekleniyor...")
            time.sleep(60)
            
        except Exception as e:
            print(f"Hata oluştu: {e}")
            time.sleep(10)
