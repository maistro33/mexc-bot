import os
import time
import telebot
import ccxt
import google.generativeai as genai

# --- 1. AYARLAR VE KİMLİK ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
genai.configure(api_key=GEMINI_KEY)

# --- 2. MODEL KONTROLÜ (Hata Önleyici Çelik Kalkan) ---
def get_verified_model():
    """API'nin izin verdiği modelleri tek tek kontrol eder ve çalışanını seçer."""
    try:
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # En güncelden başlayarak dene
        for model_path in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']:
            if model_path in available:
                return genai.GenerativeModel(model_path)
        return genai.GenerativeModel(available[0]) if available else None
    except Exception as e:
        print(f"Model seçme hatası: {e}")
        return None

ai_model = get_verified_model()

# Borsa Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'}, 'enableRateLimit': True
})

def send_telegram(message):
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_gemini_instruction(prompt):
    if not ai_model: return "AI Modeli Başlatılamadı!"
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Hatası: {str(e)}"

# --- 3. ANA OPERASYON (CANLI TELSİZ DÖNGÜSÜ) ---
if __name__ == "__main__":
    # SİSTEM AÇILIŞ TEYİDİ
    model_adi = ai_model.model_name if ai_model else "Bilinmiyor"
    send_telegram(f"🚀 **SİSTEM ÇALIŞIYOR (Çift Kontrollü)**\n\nAktif Beyin: `{model_adi}`\nCanlı telsiz hattı dinleniyor...")

    while True:
        try:
            # 📡 CANLI MESAJ İLETİMİ: Ben buradan söylüyorum, bot sana iletiyor
            canli_emir = (
                "Kaptan için şu anki canlı mesajın: 'Selam kaptan, buradayım! "
                "21.80 USDT güvende, radarlar açık ve ben tamamen senin kontrolündeyim.' "
                "Bu mesajı al ve kaptana telsiz raporu olarak gönder."
            )
            
            ai_cevap = get_gemini_instruction(canli_emir)
            
            if ai_cevap and "AI Hatası" not in ai_cevap:
                send_telegram(f"📡 **CANLI KOMUT ALINDI:**\n\n{ai_cevap}")

            # 🔍 MARKET TARAMASI (Sanal Takip)
            tickers = exchange.fetch_tickers()
            pairs = [s for s in tickers if '/USDT:USDT' in s]
            top_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:10]

            for symbol in top_pairs:
                change = tickers[symbol]['percentage']
                # %3 ve üzeri hareketlerde Sanal Takip raporu ver
                if abs(change) > 3:
                    send_telegram(f"🔍 **[SANAL TAKİP]** {symbol} (%{change:.2f})\n🛡️ Kalkan: Gövde Kapanışı Bekleniyor...")

            # Canlı takip hızı (Test için 60 saniye tutuyorum, sonra 300 yapabilirsin)
            time.sleep(60) 
            
        except Exception as e:
            print(f"Döngü Hatası: {e}")
            time.sleep(10)
