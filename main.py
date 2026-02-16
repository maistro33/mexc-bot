import os
import time
import google.generativeai as genai
from bitget.mix.market import MarketApi
from bitget.mix.order import OrderApi
import pandas as pd
import pandas_ta as ta
import requests

# --- AYARLAR VE API BAĞLANTILARI ---
# Railway Variables kısmından çekilecek
GEMINI_API = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API)
model = genai.GenerativeModel('gemini-pro')

def gemini_karar_merkezi(data_summary):
    """Verileri Gemini'ye gönderir ve mantıksal analiz ister."""
    prompt = f"""
    Sen dünyanın en iyi kripto trader'ısın. Aşağıdaki teknik verileri incele:
    {data_summary}
    
    Talimatlar:
    1. Piyasa yapıcı tuzaklarını (fakeout) ele.
    2. Eğer gerçek bir momentum veya PUMP/DUMP başlangıcı varsa 'AL' veya 'SAT' de.
    3. Kararsızsan veya risk yüksekse 'BEKLE' de.
    4. Kaldıracı 21 dolarlık kasaya göre risk-free ayarla (maks 10x).
    
    Cevap formatın sadece şu olsun:
    KARAR: [AL/SAT/BEKLE] | KALDIRAC: [X] | SEBEP: [Neden bu kararı verdin?]
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "KARAR: BEKLE | KALDIRAC: 0 | SEBEP: Baglanti hatasi."

def telegram_rapor(mesaj):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={mesaj}"
    requests.get(url)

# --- ANA DÖNGÜ ---
def start_hunting():
    telegram_rapor("🚀 Gemini AI Akıllı Beyin Aktif! Radar taraması başlıyor...")
    
    while True:
        try:
            # Burada Bitget verileri toplanacak (Kodun devamı Railway'de çalışacak)
            # Simülasyon Analizi:
            analiz_metni = "Fiyat: ETH 2000, RSI: 45, Hacim: Artıyor" 
            karar = gemini_karar_merkezi(analiz_metni)
            
            if "AL" in karar or "SAT" in karar:
                telegram_rapor(f"🎯 FIRSAT YAKALADIM!\n{karar}")
            
            time.sleep(300) # 5 dakikada bir analiz yap
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)

if __name__ == "__main__":
    start_hunting()
