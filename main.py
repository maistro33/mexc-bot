import ccxt
import telebot
import time
import os
import math

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# Bağlantı Ayarları (En Kararlı Hali)
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLARINIZ] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'timeframe': '5m'
}

active_trades = {}

# --- [3. TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['durum', 'status'])
def send_status(message):
    try:
        balance = ex.fetch_balance()
        usdt_free = balance.get('USDT', {}).get('free', 0)
        bot.reply_to(message, f"💰 **Bakiye Durumu:**\nKullanılabilir: {usdt = usdt_free:.2f} USDT\nRadar: 150 Parite Aktif 🦅")
    except Exception as e:
        bot.reply_to(message, f"❌ Bakiye çekilemedi: {str(e)}")

# --- [4. YARDIMCI FONKSİYONLAR] ---
def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        return round(amount, int(-math.log10(prec))) if prec < 1 else int(amount)
    except: return round(amount, 2)

# --- [5. ANA ANALİZ VE İŞLEM DÖNGÜSÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🦅 **BOT YENİDEN BAŞLATILDI**\nMod Ayarı: Otomatik Uyum\nBakiye Sorgulama: Aktif (/durum)")
    
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s and (markets[s]['quoteVolume'] or 0) > 1000000]
            
            for sym in symbols[:150]:
                # Basit SMC Analizi
                bars = ex.fetch_ohlcv(sym, timeframe=CONFIG['timeframe'], limit=30)
                closes = [b[4] for b in bars]
                highs = [b[2] for b in bars]
                lows = [b[3] for b in bars]

                recent_high = max(highs[-10:-1])
                recent_low = min(lows[-10:-1])

                side = None
                if closes[-1] > recent_high: side = 'buy'
                elif closes[-1] < recent_low: side = 'sell'

                if side and sym not in active_trades:
                    # Borsa Moduna Uyum Sağla
                    pos_mode = ex.fetch_position_mode(sym)
                    is_hedge = pos_mode['hedge']
                    
                    ex.set_leverage(CONFIG['leverage'], sym)
                    entry = closes[-1]
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    # Giriş
                    params = {'posSide': 'long' if side == 'buy' else 'short'} if is_hedge else {}
                    ex.create_market_order(sym, side, amount, params=params)
                    time.sleep(1)

                    # SL ve %75 TP
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    risk = entry * 0.01 # %1 Risk (Örnek)
                    stop = entry - risk if side == 'buy' else entry + risk
                    tp1 = entry + (risk * 1.5) if side == 'buy' else entry - (risk * 1.5)

                    close_params = {'stopPrice': stop, 'reduceOnly': True}
                    if is_hedge: close_params['posSide'] = 'long' if side == 'buy' else 'short'
                    
                    ex.create_order(sym, 'trigger_market', exit_side, amount, params=close_params) # Stop
                    
                    tp_params = close_params.copy()
                    tp_params['stopPrice'] = tp1
                    ex.create_order(sym, 'trigger_market', exit_side, round_amount(sym, amount * CONFIG['tp1_ratio']), params=tp_params)

                    active_trades[sym] = True
                    bot.send_message(MY_CHAT_ID, f"🎯 **İşlem Açıldı:** {sym}\nStop ve %75 TP dizildi.")

                time.sleep(0.1)
            time.sleep(15)
        except Exception:
            time.sleep(10)

if __name__ == "__main__":
    # Telegram dinlemeyi ayrı bir iş parçacığında başlat (Bakiye komutu için)
    threading.Thread(target=bot.infinity_polling).start()
    ex.load_markets()
    main_loop()
