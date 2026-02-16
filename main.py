import os
import time
import google.generativeai as genai
from bitget.mix.market import MarketApi
import requests
import pandas as pd

# --- RAILWAY'DEKİ İSİMLERİNE GÖRE AYARLADIM ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
TELE_TOKEN = os.getenv("TELE_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
# Bitget değişkenlerini de senin paneline göre eşleştiriyorum
BG_KEY = os.getenv("BITGET_API_KEY")
BG_SECRET = os.getenv("BITGET_SECRET")
BG_PW = os.getenv("BITGET_PASSWORD")

# Gemini Kurulumu
genai.configure(api_key=GEMINI_KEY)
ai_brain = genai.GenerativeModel('gemini-pro')

def telegram_yaz(mesaj):
    if not TELE_TOKEN or not MY_CHAT_ID:
        print("Telegram bilgileri eksik!")
        return
    url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": MY_CHAT_ID, "text": mesaj})

def get_market_summary():
    try:
        # Bitget'ten veri çekme simülasyonu/basit çekim
        market = MarketApi(BG_KEY, BG_SECRET, BG_PW, use_server_time=True)
        candles = market.candles('ETHUSDT', '15m', limit='20')
        # Veriyi metne dönüştür ki Gemini okuyabilsin
        return str(candles[-5:]) 
    except Exception as e:
        return f"Veri hatası: {e}"

def gemini_karar_ver(data):
    prompt = f"""
    Sen benim kripto trade asistanımsın. Veriler: {data}
    Kasa: 21 USDT. Risk: Minimal. 
    1. Pump/Dump ihtimalini değerlendir.
    2. Kararını AL, SAT veya BEKLE olarak söyle.
    3. Nedenini açıkla ve kaldıracı (max 10x) belirt.
    Format: [KARAR] | [KALDIRAC] | [NEDEN]
    """
    try:
        response = ai_brain.generate_content(prompt)
        return response.text
    except:
        return "BEKLE | Bağlantı sorunu."

def main():
    print("Sistem başlatıldı...")
    telegram_yaz("🦅 Gemini AI Core: Bağlantı kuruldu! Değişkenler eşleşti. Radar aktif!")
    
    while True:
        try:
            data = get_market_summary()
            karar = gemini_karar_ver(data)
            
            # Sadece fırsat gördüğünde mesaj atar
            if "AL" in karar or "SAT" in karar:
                telegram_yaz(f"🎯 FIRSAT ANALİZİ:\n{karar}")
            
            print(f"Döngü tamam: {karar}")
            time.sleep(300) # 5 dakikada bir kontrol
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
