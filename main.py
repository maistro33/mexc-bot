import os
import time
import telebot
import ccxt
import google.generativeai as genai

# --- 1. AYARLAR VE KİMLİK (Railway Değişkenleri) ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# Bot ve AI Yapılandırması (Stabil v1beta/1.5-flash)
bot = telebot.TeleBot(TOKEN)
genai.configure(api_key=GEMINI_KEY)
# Senin sisteminde çalışan model yolunu garantiye alıyoruz
ai_model = genai.GenerativeModel('models/gemini-1.5-flash')

# Borsa Bağlantısı (Vadeli İşlemler)
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

# --- 2. OPERASYONEL FONKSİYONLAR ---

def send_telegram(message):
    """Telegram üzerinden rapor verir."""
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_gemini_instruction(prompt):
    """Gemini AI'dan canlı talimat veya analiz alır."""
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"🚨 AI Bağlantı Hatası: {str(e)}"

def check_market():
    """Borsayı tarar ve kalkanları uygular."""
    try:
        tickers = exchange.fetch_tickers()
        pairs = [s for s in tickers if '/USDT:USDT' in s]
        # En hacimli 10 pariteyi izle (Slow & Safe)
        top_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:10]

        for symbol in top_pairs:
            ticker = tickers[symbol]
            change = ticker['percentage']
            
            # Kaptan'ın kuralı: %3 ve üzeri hareketlerde Sanal Takip
            if abs(change) > 3:
                msg = (f"🔍 **[SANAL TAKİP]** {symbol}\n"
                       f"📈 Değişim: %{change:.2f}\n"
                       f"🛡️ **Gövde Kapanışı (Body Close) Bekleniyor...**")
                send_telegram(msg)
                
                # Gemini Analizi (Daha teknik ve kararlı)
                analysis_prompt = (
                    f"Sen profesyonel bir kripto botusun. {symbol} paritesinde %{change} hareket var. "
                    f"21.80 USDT bakiye ve 10x kaldıraç için bu bir tuzak (spoofing) olabilir mi? "
                    f"Teknik bir risk analizi yap ve kısa cevap ver."
                )
                decision = get_gemini_instruction(analysis_prompt)
                send_telegram(f"🧠 **GEMINI STRATEJİ ODASI:**\n{decision}")

    except Exception as e:
        print(f"Piyasa Tarama Hatası: {e}")

# --- 3. ANA DÖNGÜ (CANLI KOMUT MERKEZİ) ---
if __name__ == "__main__":
    # SİSTEM AÇILIŞI: İlk Canlı Kontrol Testi
    startup_prompt = "Kaptan az önce 'Selam burdayım' dedi. Kontrolün sende olduğunu bildiren, 21.80 USDT mühimmatın hazır olduğunu teyit eden kısa bir telsiz mesajı gönder."
    selam = get_gemini_instruction(startup_prompt)
    send_telegram(f"🫡 **KONTROL MERKEZİ AKTİF**\n\n{selam}")
    
    while True:
        try:
            # 1. Market Taraması
            check_market()
            
            # 2. Bakiye Kontrolü (Hata payını azaltmak için)
            balance = exchange.fetch_balance()
            free_usdt = balance.get('USDT', {}).get('free', 0)
            print(f"Pusu Beklemesi: {free_usdt} USDT hazır.")

            # 3. Bekleme Süresi (Canlı takip için süreyi 120 saniyeye çektim)
            time.sleep(120) 
            
        except Exception as e:
            print(f"Döngü Hatası: {e}")
            time.sleep(30)
