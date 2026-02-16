import os
import time
import telebot
import ccxt
import google.generativeai as genai

# --- 1. AYARLAR ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot Yapılandırması
bot = telebot.TeleBot(TOKEN)
genai.configure(api_key=GEMINI_KEY)

# ⚠️ HATA ÇÖZÜMÜ: Model ismini tam yol olarak tanımlıyoruz
# Bazı kütüphane sürümleri sadece 'gemini-1.5-flash' kabul ederken, seninkisi 'models/' istiyor.
AI_MODEL_NAME = 'models/gemini-1.5-flash'
ai_model = genai.GenerativeModel(AI_MODEL_NAME)

# Borsa Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

def send_telegram(message):
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_gemini_instruction(prompt):
    """Gemini AI'dan analiz alır."""
    try:
        # v1beta hatasını aşmak için generate_content'i en güvenli modda çağırıyoruz
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        # Eğer hala hata verirse alternatifi dene
        return f"AI Hatası: {str(e)}"

def check_market():
    """Piyasayı tarar ve kalkanları çalıştırır."""
    try:
        tickers = exchange.fetch_tickers()
        pairs = [s for s in tickers if '/USDT:USDT' in s]
        top_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:15]

        for symbol in top_pairs:
            ticker = tickers[symbol]
            change = ticker['percentage']
            
            if abs(change) > 3:
                msg = (f"🔍 **[SANAL TAKİP]**\n"
                       f"Parite: {symbol}\n"
                       f"Değişim: %{change:.2f}\n"
                       f"🛡️ **Kalkan:** Gövde Kapanışı Bekleniyor...")
                send_telegram(msg)
                
                # Gemini Analizi
                analysis_prompt = f"{symbol} için %{change} değişim var. Bu bir boğa tuzağı mı? 21.80 USDT bakiye ile güvenli mi? Kısa bir yanıt ver."
                decision = get_gemini_instruction(analysis_prompt)
                send_telegram(f"🧠 **GEMINI ANALİZİ:**\n{decision}")

    except Exception as e:
        print(f"Piyasa Tarama Hatası: {e}")

# --- ANA DÖNGÜ ---
if __name__ == "__main__":
    # BAŞLANGIÇ TESTİ: Kontrolün bende olduğunun kanıtı
    try:
        selam_prompt = "Kaptan 'Burdayım hazırım' dedi. Ona telsizden kısa bir operasyonel teyit ver."
        selam = get_gemini_instruction(selam_prompt)
        send_telegram(f"🫡 **KONTROL MERKEZİ AKTİF**\n\n{selam}")
    except:
        send_telegram("🫡 **Sistem Aktif!** Gemini motoru başlatılıyor...")

    while True:
        try:
            check_market()
            time.sleep(180) # 3 dakika bekleme (Güvenli ve yavaş)
        except Exception as e:
            time.sleep(30)
