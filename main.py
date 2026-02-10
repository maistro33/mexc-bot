import ccxt
import pandas as pd
import pandas_ta as ta
import time
import requests
import telebot
from datetime import datetime

# --- KONFİGÜRASYON VE AYARLAR (Agresif Mod) ---
API_KEY = 'BURAYA_API_KEY_YAZIN'
API_SECRET = 'BURAYA_SECRET_KEY_YAZIN'
API_PASSWORD = 'BURAYA_PASSWORD_YAZIN'
TELEGRAM_TOKEN = 'BURAYA_TELEGRAM_TOKEN_YAZIN'
CHAT_ID = 'BURAYA_CHAT_ID_YAZIN'

# Strateji Parametreleri
SYMBOL_COUNT = 150          # Tarama yapılacak coin sayısı
TIMEFRAME = '5m'            # Daha hızlı sinyal için 5 dakikalık (Agresif)
LEVERAGE = 10               # Kaldıraç: 10x
USDT_AMOUNT = 20            # Giriş miktarı: 20 USDT

# Kar Al ve Zarar Durdur (Sizin istediğiniz %75 TP1 ayarıyla)
CLOSE_PERCENTAGE_TP1 = 0.75 
TP1_RATIO = 0.015           # %1.5 kârda TP1
TP2_RATIO = 0.030           # %3.0 kârda TP2
STOP_LOSS_RATIO = 0.01      # %1 stop

# Agresiflik Ayarları (Strateji aynı, onay eşikleri düşük)
VOLUME_CONFIRMATION_FACTOR = 1.2  # %20 hacim artışı yeterli (Önceden 1.5 idi)
BODY_CLOSE_ONLY = True           # Gövde kapanış onayı hala aktif (Güvenlik için)

# --- BOT BAŞLANGIÇ ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)
bitget = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'password': API_PASSWORD,
    'options': {'defaultType': 'swap'}
})

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}"
        requests.get(url)
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_symbols():
    try:
        markets = bitget.fetch_markets()
        symbols = [m['symbol'] for m in markets if m['quote'] == 'USDT' and m['active']]
        # Hacme göre sırala ve ilk 150'yi al
        return symbols[:SYMBOL_COUNT]
    except:
        return []

def get_data(symbol):
    try:
        ohlcv = bitget.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except:
        return None

def check_strategy(df):
    if df is None or len(df) < 20: return None
    
    # Göstergeler
    df['ema20'] = ta.ema(df['close'], length=20)
    df['rsi'] = ta.rsi(df['close'], length=14)
    avg_volume = df['volume'].rolling(window=10).mean().iloc[-2]
    current_volume = df['volume'].iloc[-1]
    
    last_close = df['close'].iloc[-1]
    prev_high = df['high'].iloc[-5:-1].max()
    prev_low = df['low'].iloc[-5:-1].min()
    
    # Agresif Onay: Hacim ortalamanın üzerindeyse ve gövde kırılımı varsa
    volume_ok = current_volume > (avg_volume * VOLUME_CONFIRMATION_FACTOR)
    
    # LONG: Fiyat önceki tepenin üzerinde kapandıysa ve hacim destekliyorsa
    if last_close > prev_high and volume_ok:
        return 'buy'
    
    # SHORT: Fiyat önceki dibin altında kapandıysa ve hacim destekliyorsa
    if last_close < prev_low and volume_ok:
        return 'sell'
        
    return None

def execute_trade(symbol, side):
    try:
        # Hedge Modu Onayı (Zorunlu)
        bitget.set_position_mode(True, symbol)
        bitget.set_leverage(LEVERAGE, symbol)
        
        amount = USDT_AMOUNT / bitget.fetch_ticker(symbol)['last']
        
        # Ana Emir (Hedge Mode için 'long' veya 'short' olarak gönderilir)
        pos_side = 'long' if side == 'buy' else 'short'
        order = bitget.create_market_order(symbol, side, amount, params={'pos_side': pos_side})
        
        msg = f"🚀 AGRESİF İŞLEM AÇILDI\nSembol: {symbol}\nYön: {pos_side}\nMiktar: {USDT_AMOUNT} USDT"
        send_telegram_msg(msg)
        
    except Exception as e:
        print(f"İşlem Hatası ({symbol}): {e}")

def main():
    send_telegram_msg("⚡ Bot Agresif Modda Başlatıldı! 150 Coin Taranıyor...")
    while True:
        symbols = get_symbols()
        for symbol in symbols:
            df = get_data(symbol)
            signal = check_strategy(df)
            
            if signal:
                execute_trade(symbol, signal)
                time.sleep(2) # Borsayı yormamak için
                
        print(f"{datetime.now()} - Tarama Tamamlandı.")
        time.sleep(15) # 15 saniyede bir yeni tarama

if __name__ == "__main__":
    main()
