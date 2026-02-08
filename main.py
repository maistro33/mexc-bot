import ccxt
import pandas as pd
import time
import requests

# --- BURAYI TELEFONUNUZDAN DOLDURUN ---
API_KEY = 'MEXC_API_KEYINIZ'
API_SECRET = 'MEXC_SECRET_KEYINIZ'
TELEGRAM_TOKEN = 'BOT_TOKENINIZ'
TELEGRAM_CHAT_ID = 'CHAT_ID_NUMARANIZ'

# AYARLARIMIZ
USDT_AMOUNT = 20
LEVERAGE = 10
SYMBOL = 'PNUT/USDT' # Test koini

# MEXC BAGLANTISI
exchange = ccxt.mexc({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'options': {'defaultType': 'swap'}
})

def send_msg(text):
    requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={text}")

def islem_yap():
    try:
        # Piyasayı kontrol et ve yön seç
        ticker = exchange.fetch_ticker(SYMBOL)
        last_price = ticker['last']
        
        # Miktar ve Kaldıraç
        exchange.set_leverage(LEVERAGE, SYMBOL)
        amount = (USDT_AMOUNT * LEVERAGE) / last_price
        
        # TEST İŞLEMİNİ AÇ (Marketten girer)
        order = exchange.create_market_order(SYMBOL, 'buy', amount)
        
        send_msg(f"✅ SADIK BEY, MEXC İŞLEMİ AÇILDI!\nKoin: {SYMBOL}\nMiktar: 20 USDT\nKaldıraç: 10x")
        print("İşlem açıldı, bot durduruluyor.")
        
    except Exception as e:
        send_msg(f"❌ Hata: {e}")

if __name__ == "__main__":
    send_msg("🤖 Bot MEXC için tetikte... İlk fırsatta işlem açacak.")
    islem_yap()
