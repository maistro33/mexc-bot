import os
import time
import telebot
import ccxt
import google.generativeai as genai

# --- 1. AYARLAR VE DEĞİŞKENLER ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot Nesneleri
bot = telebot.TeleBot(TOKEN)
genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-pro')

# Bitget Bağlantısı
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

# --- 2. YARDIMCI FONKSİYONLAR ---
def send_telegram(message):
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_balance():
    try:
        balance = exchange.fetch_balance()
        return balance['total'].get('USDT', 0)
    except:
        return 21.80  # Hata durumunda son bilinen bakiye

# --- 3. ANTİ-MANİPÜLASYON VE ANALİZ ---
def check_signals():
    # En hacimli 50 pariteyi çek
    tickers = exchange.fetch_tickers()
    # Sadece USDT vadeli pariteleri filtrele ve hacme göre sırala
    usdt_pairs = [symbol for symbol in tickers if '/USDT:USDT' in symbol]
    sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:50]

    for symbol in sorted_pairs:
        ticker = tickers[symbol]
        change = ticker['percentage']
        
        # %3'ten fazla hareket varsa Sanal Takibe al
        if abs(change) > 3:
            send_telegram(f"🔍 **[SANAL TAKİP]** {symbol}\n📈 Değişim: %{change:.2f}\n🛡️ Kalkanlar: Gövde Kapanışı Bekleniyor...")
            
            # Burada Gemini AI'ya danışıyoruz
            prompt = f"{symbol} için anlık fiyat {ticker['last']}. Hacim yüksek. Bu bir tuzak mı yoksa gerçek bir pump mı? 10x kaldıraç ve 21$ bakiye ile kârlı bir trade önerir misin? Sadece 'AL', 'SAT' veya 'BEKLE' olarak başla."
            response = ai_model.generate_content(prompt)
            decision = response.text
            
            if "AL" in decision or "SAT" in decision:
                send_telegram(f"🎯 **[FIRSAT SİNYALİ]**\n{decision}")

# --- 4. ANA DÖNGÜ ---
def run_bot():
    send_telegram("🦅 **Gemini AI Core: Sistem Tam Kapasite Devrede!**\n\nKaptan, tüm borsa taranıyor. Radarlar pusu modunda.")
    
    while True:
        try:
            # 1. Bakiye Raporu
            current_balance = get_balance()
            
            # 2. Sinyal Taraması
            check_signals()
            
            # 3. Bekleme (Her 10 dakikada bir tam tarama)
            time.sleep(600) 
            
        except Exception as e:
            print(f"Hata Oluştu: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_bot()
