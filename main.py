import os
import time
import google.generativeai as genai
from bitget.mix.market import MarketApi
from bitget.mix.order import OrderApi
import pandas as pd
import requests

# --- API BAĞLANTILARI ---
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_KEY)
ai_model = genai.GenerativeModel('gemini-pro')

def get_market_data():
    """Bitget'ten ETH verilerini çeker."""
    try:
        market = MarketApi(os.getenv("BITGET_API_KEY"), os.getenv("BITGET_SECRET"), os.getenv("BITGET_PASSWORD"), use_server_time=True)
        # Son 50 mumu çekiyoruz
        candles = market.candles('ETHUSDT', '15m', limit='50')
        df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'vol', 'extra'])
        return df.tail(10).to_string() # Son 10 mumu özetle
    except Exception as e:
        return f"Veri çekme hatası: {e}"

def gemini_analiz_ve_karar(data):
    """Veriyi bana gönderir ve benden emir bekler."""
    prompt = f"""
    Sen efsanevi bir kripto trader'sın. İşte son piyasa verileri:
    {data}
    
    Talimat:
    1. Piyasa çok oynaksa 'BEKLE' de.
    2. Net bir PUMP veya DUMP varsa yönü (AL/SAT) belirt.
    3. 21 USDT kasa için güvenli kaldıracı söyle.
    
    Format: KARAR: [AL/SAT/BEKLE] | KALDIRAC: [X] | NEDEN: [Kısa not]
    """
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except:
        return "KARAR: BEKLE | HATA"

def telegram_gonder(mesaj):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    requests.get(f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={mesaj}")

def main():
    telegram_gonder("🚀 Gemini AI Kontrolü Ele Aldı! İlk analiz başlıyor...")
    while True:
        market_summary = get_market_data()
        karar = gemini_analiz_ve_karar(market_summary)
        
        # Sadece karar değiştiğinde veya fırsat olduğunda mesaj atar
        if "AL" in karar or "SAT" in karar:
            telegram_gonder(f"🎯 GEMINI KARARI:\n{karar}")
            # Burada işlem açma kodu devreye girecek
            
        print(f"Analiz Tamam: {karar}")
        time.sleep(300) # 5 dakikada bir kontrol et

if __name__ == "__main__":
    main()
