import os
import time
import telebot
import ccxt
import google.generativeai as genai

# --- 1. AYARLAR VE KİMLİK (Railway'den Çeker) ---
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

# Bitget Bağlantısı (Vadeli İşlemler - Swap)
exchange = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})

# --- 2. FONKSİYONLAR ---

def send_telegram(message):
    """Telegram üzerinden rapor verir."""
    try:
        bot.send_message(CHAT_ID, message, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_gemini_instruction(prompt):
    """Gemini AI'dan stratejik karar alır."""
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except:
        return "BEKLE"

def check_market():
    """Borsayı tarar ve kalkanları kontrol eder."""
    try:
        # En hacimli pariteleri çekiyoruz
        tickers = exchange.fetch_tickers()
        # Sadece USDT vadeli pariteler
        pairs = [s for s in tickers if '/USDT:USDT' in s]
        sorted_pairs = sorted(pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:30]

        for symbol in sorted_pairs:
            ticker = tickers[symbol]
            change = ticker['percentage']
            
            # Senin kuralın: %3+ hareket varsa Sanal Takip başlat
            if abs(change) > 3:
                # 🛡️ KALKAN 1: Sanal Takip Raporu
                send_telegram(f"🔍 **[SANAL TAKİP]** {symbol}\n📈 Değişim: %{change:.2f}\n🛡️ Durum: Gövde Kapanışı ve Hacim Onayı Bekleniyor...")
                
                # 🛡️ KALKAN 2: Gemini Analizi
                prompt = f"{symbol} paritesinde %{change} hareket var. Hacim yüksek. Bu bir tuzak (spoofing) olabilir mi? Gövde kapanışı onayıyla 10x kaldıraç için güvenli mi? Sadece kısa bir analiz ve KARAR (AL/SAT/BEKLE) ver."
                decision = get_gemini_instruction(prompt)
                
                # Eğer Gemini onay verirse (Şimdilik sadece raporluyoruz)
                if "AL" in decision or "SAT" in decision:
                    send_telegram(f"🎯 **[FIRSAT ONAYLANDI]**\n{decision}")

    except Exception as e:
        print(f"Market Tarama Hatası: {e}")

# --- 3. ANA DÖNGÜ (OPERASYON MERKEZİ) ---
if __name__ == "__main__":
    # Başlangıç Mesajı (Kontrolün bende olduğunun kanıtı)
    startup_msg = get_gemini_instruction("Kaptan'a (kullanıcıya) sistemin senin kontrolünde açıldığını, 21.80 USDT'nin pusuda olduğunu ve radarların çalıştığını anlatan çok kısa, havalı bir selam yaz.")
    send_telegram(f"🫡 **SİSTEM ŞAHLANDI**\n\n{startup_msg}")
    
    while True:
        try:
            # Bakiyeyi kontrol et ve raporla (Her döngüde değil, 30 dakikada bir yapabilirsin)
            check_market()
            
            # Senin istediğin "Slow & Risk-Free" strateji için 5 dakika (300 saniye) bekleme
            time.sleep(300) 
            
        except Exception as e:
            print(f"Döngü Hatası: {e}")
            time.sleep(60)
