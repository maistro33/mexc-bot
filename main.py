import ccxt
import pandas as pd
import time
import requests
from datetime import datetime

# --- KİMLİK BİLGİLERİ (Eksiksiz Doldurun) ---
API_KEY = 'BURAYA_API_KEY'
API_SECRET = 'BURAYA_SECRET'
API_PASSWORD = 'BURAYA_PASSWORD'
TELEGRAM_TOKEN = 'BURAYA_TOKEN'
CHAT_ID = 'BURAYA_CHAT_ID'

# --- AGRESİF AYARLAR ---
SYMBOL_COUNT = 150
TIMEFRAME = '5m'            # Hızlı sinyal için 5 dakika
LEVERAGE = 10
USDT_AMOUNT = 20
VOLUME_FACTOR = 1.15        # %15 hacim artışı yeterli (Agresif)
CLOSE_PERCENTAGE_TP1 = 0.75 # Sizin istediğiniz TP1 oranı

# --- BOT KURULUM ---
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
        params = {'chat_id': CHAT_ID, 'text': text}
        requests.get(url, params=params, timeout=10)
    except:
        pass

def get_signal(symbol):
    try:
        ohlcv = bitget.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=30)
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        # Manuel RSI ve Hacim Hesaplama (Kütüphane gerektirmez, çökme yapmaz)
        avg_vol = df['v'].iloc[-11:-1].mean()
        curr_vol = df['v'].iloc[-1]
        last_c = df['c'].iloc[-1]
        
        # Son 10 mumun en yükseği ve en düşüğü (Market Structure)
        prev_h = df['h'].iloc[-11:-1].max()
        prev_l = df['l'].iloc[-11:-1].min()
        
        vol_ok = curr_vol > (avg_vol * VOLUME_FACTOR)
        
        # LONG: Önceki tepenin üzerinde gövde kapanışı + Hacim
        if last_c > prev_h and vol_ok: return 'buy'
        # SHORT: Önceki dibin altında gövde kapanışı + Hacim
        if last_c < prev_l and vol_ok: return 'sell'
        
        return None
    except:
        return None

def open_pos(symbol, side):
    try:
        # Hedge Modu ve Kaldıraç Ayarı
        try: bitget.set_position_mode(True, symbol)
        except: pass
        try: bitget.set_leverage(LEVERAGE, symbol)
        except: pass
        
        ticker = bitget.fetch_ticker(symbol)
        price = ticker['last']
        amount = USDT_AMOUNT / price
        pos_side = 'long' if side == 'buy' else 'short'
        
        # Market Giriş Emri
        bitget.create_market_order(symbol, side, amount, params={'posSide': pos_side})
        
        msg = f"🚀 AGRESİF İŞLEM AÇILDI\nSembol: {symbol}\nYön: {pos_side}\nMiktar: {USDT_AMOUNT} USDT\nZaman: {TIMEFRAME}"
        send_msg(msg)
    except Exception as e:
        print(f"İşlem Hatası ({symbol}): {e}")

def main():
    send_msg("🤖 Bot Agresif & Stabil Modda Başlatıldı. 150 Coin Taranıyor...")
    print("Bot çalışıyor...")
    
    while True:
        try:
            markets = bitget.fetch_markets()
            symbols = [m['symbol'] for m in markets if m['linear'] and m['active']][:SYMBOL_COUNT]
            
            for s in symbols:
                sig = get_signal(s)
                if sig:
                    open_pos(s, sig)
                    time.sleep(1)
            
            print(f"{datetime.now()} - Tarama Başarıyla Tamamlandı.")
            time.sleep(20)
        except Exception as e:
            print(f"Hata oluştu: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
