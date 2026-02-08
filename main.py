import ccxt
import pandas as pd
import time
import requests

# --- KULLANICI AYARLARI (SADIK BEY ÖZEL) ---
API_KEY = 'BURAYA_BINANCE_API_KEY_YAZIN'
API_SECRET = 'BURAYA_BINANCE_SECRET_YAZIN'
TELEGRAM_TOKEN = 'BURAYA_TELEGRAM_BOT_TOKEN_YAZIN'
TELEGRAM_CHAT_ID = 'BURAYA_CHAT_ID_YAZIN'

# BOT PARAMETRELERİ
USDT_AMOUNT = 20          # Her işlem için 20 USDT
LEVERAGE = 10             # 10x Kaldıraç
CLOSE_PERCENT_TP1 = 0.75  # %75 Kâr Al (TP1)
SYMBOLS = ['PNUT/USDT', 'GOAT/USDT', 'TURBO/USDT', 'FARTCOIN/USDT', 'MOODENG/USDT'] # Takip listesi

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'options': {'defaultType': 'future'}
})

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={message}"
    requests.get(url)

def get_data(symbol):
    bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def open_position(symbol, side):
    try:
        # Kaldıraç ayarla
        exchange.set_leverage(LEVERAGE, symbol)
        
        # Miktarı hesapla (20 USDT'lik kaç adet koin alınır?)
        price = exchange.fetch_ticker(symbol)['last']
        amount = (USDT_AMOUNT * LEVERAGE) / price
        
        order = exchange.create_market_order(symbol, side, amount)
        send_telegram(f"🎯 SADIK BEY, İŞLEM AÇILDI!\nKoin: {symbol}\nYön: {side}\nMiktar: {USDT_AMOUNT} USDT\nKaldıraç: {LEVERAGE}x")
        return order
    except Exception as e:
        send_telegram(f"⚠️ Hata oluştu: {e}")

def check_logic():
    for symbol in SYMBOLS:
        df = get_data(symbol)
        last_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]
        high_prev = df['high'].iloc[-2]
        low_prev = df['low'].iloc[-2]

        # --- HIZLI TEST MANTIĞI (Filtreler Esnetildi) ---
        
        # Hızlı Short: Eğer son mum bir önceki mumun en düşüğünün altında kapandıysa (Basit MSS)
        if last_close < low_prev:
            open_position(symbol, 'sell')
            break # Sadece 1 işlem alması için durduruyoruz

        # Hızlı Long: Eğer son mum bir önceki mumun en yükseğinin üstünde kapandıysa
        elif last_close > high_prev:
            open_position(symbol, 'buy')
            break # Sadece 1 işlem alması için durduruyoruz

print("Bot başlatıldı... Sadık Bey, ilk fırsatta işlem açılacak.")
while True:
    try:
        check_logic()
        time.sleep(60) # Her dakika kontrol et
    except Exception as e:
        print(f"Hata: {e}")
        time.sleep(10)
