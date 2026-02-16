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

bot = telebot.TeleBot(TOKEN)
genai.configure(api_key=GEMINI_KEY)

# --- 2. AKILLI MODEL SEÇİCİ ---
def get_working_model():
    """Sistemde aktif olan en uygun Gemini modelini bulur."""
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    # Tercih sıramız: 1.5-flash, 1.5-pro, en son hangisi varsa
    for preferred in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']:
        if preferred in available_models:
            return genai.GenerativeModel(preferred)
    # Eğer hiçbiri yoksa listedeki ilk modeli seç
    return genai.GenerativeModel(available_models[0]) if available_models else None

ai_model = get_working_model()

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
    try:
        if ai_model:
            response = ai_model.generate_content(prompt)
            return response.text
        return "AI Modeli hazır değil."
    except Exception as e:
        return f"🚨 AI Hatası: {str(e)}"

def check_market():
    try:
        tickers = exchange.fetch_tickers()
        pairs = [s for s in tickers if '/USDT:USDT' in s]
        top_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:10]

        for symbol in top_pairs:
            ticker = tickers[symbol]
            change = ticker['percentage']
            
            # Senin kuralın: %3+ hareket
            if abs(change) > 3:
                msg = f"🔍 **[SANAL TAKİP]** {symbol}\n📈 Değişim: %{change:.2f}\n🛡️ Kalkan: Onay Bekleniyor..."
                send_telegram(msg)
                
                analysis_prompt = f"{symbol} paritesinde %{change} hareket var. Bu bir manipülasyon mu? 21.80 USDT bakiye için güvenli mi? Kısa yanıt ver."
                decision = get_gemini_instruction(analysis_prompt)
                send_telegram(f"🧠 **GEMINI ANALİZİ:**\n{decision}")

    except Exception as e:
        print(f"Hata: {e}")

# --- ANA DÖNGÜ ---
if __name__ == "__main__":
    try:
        model_name = ai_model.model_name if ai_model else "Bulunamadı"
        send_telegram(f"🫡 **KAPTAN, SİSTEM ŞAHLANDI!**\n\nAktif Beyin: `{model_name}`\n21.80 USDT mühimmat namluda. Kontrol bende! 🦅")
    except:
        send_telegram("🫡 Bot aktif, radarlar dönüyor!")

    while True:
        try:
            check_market()
            time.sleep(180) # 3 dakika bekleme
        except Exception as e:
            time.sleep(30)
