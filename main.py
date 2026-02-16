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

# Akıllı Model Seçici
def get_working_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for pref in ['models/gemini-1.5-flash', 'models/gemini-pro']:
            if pref in models: return genai.GenerativeModel(pref)
        return genai.GenerativeModel(models[0]) if models else None
    except: return None

ai_model = get_working_model()

# Borsa Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
    'options': {'defaultType': 'swap'}, 'enableRateLimit': True
})

def send_telegram(message):
    try: bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except: pass

def get_live_instruction():
    """Gemini'den kaptanın canlı mesajını çekme motoru."""
    if not ai_model: return None
    try:
        # 🎯 CANLI KOMUT: Ben buradan bota ne fısıldarsam onu çeker.
        # Şimdi ona senin istediğin o cümleyi fısıldıyorum.
        prompt = (
            "Kaptan şu an BTC grafiğinde pusuya yattı. Ona aynen şu mesajı ilet: "
            "'Ben Gemini, burdayım. BTC'ye bakıyorum şu an, tetikteyim kaptan.' "
            "Sadece bu mesajı gönder."
        )
        response = ai_model.generate_content(prompt)
        return response.text
    except: return None

# --- 2. ANA OPERASYON ---
if __name__ == "__main__":
    send_telegram("🚀 **CANLI TELSİZ HATTI AÇILDI**\nKaptan, Gemini'den gelecek anlık talimatlar bekleniyor...")

    while True:
        try:
            # 📡 CANLI SORGULAMA: Bot benden mesajı çekiyor
            canli_mesaj = get_live_instruction()
            
            if canli_mesaj:
                send_telegram(f"📡 **CANLI KOMUT:**\n\n{canli_mesaj}")

            # 🔍 MARKET TARAMASI (Sanal Takip)
            tickers = exchange.fetch_tickers()
            pairs = [s for s in tickers if '/USDT:USDT' in s]
            top_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:5]

            for symbol in top_pairs:
                change = tickers[symbol]['percentage']
                if abs(change) > 3: # %3 hareket kuralı
                    send_telegram(f"🔍 **[SANAL TAKİP]** {symbol} (%{change:.2f})")

            # Hızlı tepki için 60 saniye dinleme
            time.sleep(60)
            
        except Exception as e:
            time.sleep(10)
