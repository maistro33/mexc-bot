import ccxt
import pandas as pd
import pandas_ta as ta
import time
import requests
import telebot
from datetime import datetime

# --- KİMLİK BİLGİLERİ (Lütfen Eksiksiz Doldurun) ---
API_KEY = 'BURAYA_API_KEY'
API_SECRET = 'BURAYA_SECRET'
API_PASSWORD = 'BURAYA_PASSWORD'
TELEGRAM_TOKEN = 'BURAYA_TOKEN'
CHAT_ID = 'BURAYA_CHAT_ID'

# --- AGRESİF AYARLAR (Strateji Aynı, Onaylar Hızlı) ---
SYMBOL_COUNT = 150
TIMEFRAME = '5m'            # 5 dakikalık mumlar (Hızlı sinyal)
LEVERAGE = 10               # 10x kaldıraç
USDT_AMOUNT = 20            # 20 USDT giriş
CLOSE_PERCENTAGE_TP1 = 0.75 # TP1'de %75 kapatma

# Strateji Onay Eşikleri (Agresif Mod)
VOLUME_FACTOR = 1.15        # %15 hacim artışı yeterli
BODY_CLOSE_ONLY = True      # Sahte iğnelerden koruma hala aktif

# --- KURULUM ---
bitget = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'password': API_PASSWORD,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def send_msg(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': CHAT_ID, 'text': text}, timeout=10)
    except: pass

def get_signal(symbol):
    try:
        ohlcv = bitget.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=50)
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # Göstergeler
        avg_vol = df['v'].rolling(20).mean().iloc[-2]
        curr_vol = df['v'].iloc[-1]
        last_c = df['c'].iloc[-1]
        prev_h = df['h'].iloc[-10:-1].max()
        prev_l = df['l'].iloc[-10:-1].min()
        
        # Agresif Koşul: Hacim + Kırılım
        vol_ok = curr_vol > (avg_vol * VOLUME_FACTOR)
        
        if last_c > prev_h and vol_ok: return 'buy'
        if last_c < prev_l and vol_ok: return 'sell'
        return None
    except: return None

def open_pos(symbol, side):
    try:
        # Hedge Mode ve Kaldıraç Zorlaması
        try: bitget.set_position_mode(True, symbol)
        except: pass
        bitget.set_leverage(LEVERAGE, symbol)
        
        price = bitget.fetch_ticker(symbol)['last']
        amount = USDT_AMOUNT / price
        pos_side = 'long' if side == 'buy' else 'short'
        
        # Ana Giriş
        bitget.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        
        # TP/SL Hesaplama
        tp_price = price * 1.02 if side == 'buy' else price * 0.98
        sl_price = price * 0.99 if side == 'buy' else price * 1.01
        
        send_msg(f"🚀 İŞLEM AÇILDI ({TIMEFRAME} Agresif)\nSembol: {symbol}\nYön: {pos_side}\nBakiye: {USDT_AMOUNT} USDT")
    except Exception as e:
        print(f"Hata: {e}")

def main():
    send_msg("🤖 Bot Agresif Modda Yeniden Başlatıldı. 150 Coin Taranıyor...")
    while True:
        try:
            markets = bitget.fetch_markets()
            symbols = [m['symbol'] for m in markets if m['linear'] and m['active']][:SYMBOL_COUNT]
            
            for s in symbols:
                sig = get_signal(s)
                if sig:
                    open_pos(s, sig)
                    time.sleep(1)
            
            print(f"{datetime.now()} - Tarama Bitti.")
            time.sleep(20)
        except Exception as e:
            print(f"Döngü Hatası: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
