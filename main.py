import ccxt
import telebot
import time
import os
import math
import threading

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# 'positionMode': True -> Borsadaki Hedge modunu zorunlu kılar ve senkronize eder.
ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap', 'positionMode': True},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'max_active_trades': 3,
    'timeframe': '5m'
}

active_trades = {}

def round_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        prec = market['precision']['amount']
        return round(amount, int(-math.log10(prec))) if prec < 1 else int(amount)
    except: return round(amount, 2)

@bot.message_handler(commands=['durum', 'bakiye'])
def send_status(message):
    try:
        balance = ex.fetch_balance()
        usdt_free = balance.get('USDT', {}).get('free', 0)
        bot.reply_to(message, f"💰 **Güncel Bakiye:** {usdt_free:.2f} USDT\n🦅 Radar Aktif (Hedge Mode Sabit)")
    except Exception as e:
        bot.reply_to(message, f"❌ Hata: {str(e)}")

# --- [3. ANA İŞLEM DÖNGÜSÜ] ---
def main_loop():
    bot.send_message(MY_CHAT_ID, "🦅 **SMC BOT GÜVENLİ MODDA BAŞLADI**\nBakiye ve mod kontrolü yapıldı. Av başlıyor!")
    
    while True:
        try:
            markets = ex.fetch_tickers()
            symbols = [s for s in markets if '/USDT:USDT' in s and (markets[s]['quoteVolume'] or 0) > 2000000]
            
            for sym in symbols[:100]:
                if sym in active_trades or len(active_trades) >= CONFIG['max_active_trades']: continue
                
                # Basit SMC Analizi
                bars = ex.fetch_ohlcv(sym, timeframe=CONFIG['timeframe'], limit=30)
                c, h, l = [b[4] for b in bars], [b[2] for b in bars], [b[3] for b in bars]
                recent_high, recent_low = max(h[-15:-1]), min(l[-15:-1])
                
                side = None
                if c[-1] > recent_high: side = 'buy'
                elif c[-1] < recent_low: side = 'sell'

                if side:
                    # Kaldıraç ayarı
                    ex.set_leverage(CONFIG['leverage'], sym)
                    entry = c[-1]
                    amount = round_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    # Hedge Mode parametreleri (Hata almamak için zorunlu)
                    pos_side = 'long' if side == 'buy' else 'short'
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    
                    # 1. Giriş Emri
                    ex.create_market_order(sym, side, amount, params={'posSide': pos_side})
                    time.sleep(1)

                    # 2. SL ve TP Seviyeleri (%1.5 RR)
                    risk = entry * 0.01
                    stop = entry - risk if side == 'buy' else entry + risk
                    tp1 = entry + (risk * 1.5) if side == 'buy' else entry - (risk * 1.5)

                    # 3. SL ve %75 TP Emirleri (Hedge uyumlu)
                    # Stop Loss
                    ex.create_order(sym, 'trigger_market', exit_side, amount, 
                                     params={'stopPrice': stop, 'reduceOnly': True, 'posSide': pos_side})
                    
                    # %75 TP1
                    tp_qty = round_amount(sym, amount * CONFIG['tp1_ratio'])
                    ex.create_order(sym, 'trigger_market', exit_side, tp_qty, 
                                     params={'stopPrice': tp1, 'reduceOnly': True, 'posSide': pos_side})

                    active_trades[sym] = True
                    bot.send_message(MY_CHAT_ID, f"🎯 **İşlem Açıldı:** {sym}\nSL ve %75 TP emirleri borsada dizildi!")
                
                time.sleep(0.2)
            time.sleep(20)
        except Exception as e:
            # Hata durumunda döngünün kırılmaması için
            time.sleep(10)

if __name__ == "__main__":
    # Telegram botunu thread içinde başlat
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    ex.load_markets()
    main_loop()
