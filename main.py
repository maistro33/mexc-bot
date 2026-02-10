import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {
        'defaultType': 'swap',
        'hedged': True,           # Hedge Mode garanti
    },
    'enableRateLimit': True
})

bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR] ---
CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'max_active_trades': 4,
    'rr_target': 1.3,
    'timeframe': '5m'
}

active_trades = {}
scanned_list = []

# --- [3. YENİ TP/SL FONKSİYONU] ---
def place_tpsl(symbol, plan_type, trigger_price, hold_side, qty):
    """plan_type: 'pos_profit' veya 'pos_loss'"""
    try:
        exit_side = 'sell' if hold_side == 'long' else 'buy'
        
        params = {
            'planType': plan_type,
            'triggerPrice': ex.price_to_precision(symbol, trigger_price),
            'triggerType': 'mark_price',
            'holdSide': hold_side,
            'reduceOnly': True,
            'executePrice': '0',
        }
        
        if qty:
            params['size'] = ex.amount_to_precision(symbol, qty)
        
        order = ex.create_order(
            symbol=symbol,
            type='market',
            side=exit_side,
            amount=qty,
            params=params
        )
        
        bot.send_message(MY_CHAT_ID, f"✅ {plan_type.upper().replace('_', ' ')} konuldu → {symbol} @ {trigger_price}")
        return order
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ TPSL Hatası ({plan_type}) {symbol}: {str(e)[:150]}")
        print(f"TPSL Error: {e}")
        return None

# --- [4. TAKİP VE RAPORLAMA] ---
def report_loop():
    while True:
        try:
            time.sleep(300)
            msg = f"📡 **SMC RADAR AKTİF**\n🔍 Taranan: {len(scanned_list)}\n📈 Aktif: {len(active_trades)}"
            bot.send_message(MY_CHAT_ID, msg)
        except: pass

def monitor_trade(symbol):
    while symbol in active_trades:
        try:
            time.sleep(15)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0].get('contracts', 0)) == 0:
                if symbol in active_trades:
                    del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} işlemi kapandı.")
                break
        except: break

# --- [5. TEST İÇİN HEMEN İŞLEM AÇMA KOMUTLARI] ---
@bot.message_handler(commands=['testlong'])
def test_long(message):
    symbol = 'BTC/USDT:USDT'   # İstediğin coini buraya yaz (veya mesajdan al)
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        entry = ticker['last']
        stop = entry * 0.985          # %1.5 stop (test için)
        tp1 = entry + (entry - stop) * CONFIG['rr_target']
        
        amount = ex.amount_to_precision(symbol, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
        
        # Giriş
        ex.create_order(symbol, 'market', 'buy', amount, params={'posSide': 'long'})
        time.sleep(2.5)   # Pozisyon oluşsun
        
        # TP ve SL
        place_tpsl(symbol, 'pos_loss', stop, 'long', amount)
        tp1_qty = ex.amount_to_precision(symbol, float(amount) * CONFIG['tp1_ratio'])
        place_tpsl(symbol, 'pos_profit', tp1, 'long', tp1_qty)
        
        active_trades[symbol] = True
        threading.Thread(target=monitor_trade, args=(symbol,), daemon=True).start()
        
        bot.reply_to(message, f"🚀 TEST LONG AÇILDI\n{symbol}\nEntry: {entry}\nStop: {stop}\nTP: {tp1}")
    except Exception as e:
        bot.reply_to(message, f"Test hatası: {str(e)}")

@bot.message_handler(commands=['testshort'])
def test_short(message):
    symbol = 'BTC/USDT:USDT'
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        entry = ticker['last']
        stop = entry * 1.015
        tp1 = entry - (stop - entry) * CONFIG['rr_target']
        
        amount = ex.amount_to_precision(symbol, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
        
        ex.create_order(symbol, 'market', 'sell', amount, params={'posSide': 'short'})
        time.sleep(2.5)
        
        place_tpsl(symbol, 'pos_loss', stop, 'short', amount)
        tp1_qty = ex.amount_to_precision(symbol, float(amount) * CONFIG['tp1_ratio'])
        place_tpsl(symbol, 'pos_profit', tp1, 'short', tp1_qty)
        
        active_trades[symbol] = True
        threading.Thread(target=monitor_trade, args=(symbol,), daemon=True).start()
        
        bot.reply_to(message, f"🚀 TEST SHORT AÇILDI\n{symbol}\nEntry: {entry}\nStop: {stop}\nTP: {tp1}")
    except Exception as e:
        bot.reply_to(message, f"Test hatası: {str(e)}")

# --- [6. ANA DÖNGÜ (eski mantık korunarak)] ---
def main_loop():
    global scanned_list
    while True:
        try:
            markets = ex.fetch_tickers()
            sorted_symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x].get('quoteVolume') or 0,
                reverse=True
            )[:150]
            
            scanned_list = sorted_symbols
            
            for sym in sorted_symbols:
                if sym in active_trades: continue
                
                side, entry, stop, msg_type = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = ex.amount_to_precision(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    
                    pos_side = 'long' if side == 'buy' else 'short'
                    exit_side = 'sell' if side == 'buy' else 'buy'
                    
                    if side == 'buy':
                        tp1 = entry + ((entry - stop) * CONFIG['rr_target'])
                    else:
                        tp1 = entry - ((stop - entry) * CONFIG['rr_target'])

                    # Giriş
                    ex.create_order(sym, 'market', side, amount, params={'posSide': pos_side})
                    active_trades[sym] = True
                    time.sleep(2.5)

                    # TP/SL
                    place_tpsl(sym, 'pos_loss', stop, pos_side, amount)
                    tp1_qty = ex.amount_to_precision(sym, float(amount) * CONFIG['tp1_ratio'])
                    place_tpsl(sym, 'pos_profit', tp1, pos_side, tp1_qty)

                    bot.send_message(MY_CHAT_ID, f"🚀 **YENİ {side.upper()} İŞLEMİ**\n{sym}\nGiriş: {entry}\nStop: {stop}\nTP1: {tp1}")
                    threading.Thread(target=monitor_trade, args=(sym,), daemon=True).start()
                
                time.sleep(0.1)
            time.sleep(15)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(10)

# SMC analiz fonksiyonun (değişmedi)
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 3 or now_sec > 57: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=50)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        swing_low = min(l[-15:-1])
        liq_taken_long = l[-1] < swing_low
        recent_high = max(h[-8:-1])
        mss_long = c[-1] > recent_high 
        
        swing_high = max(h[-15:-1])
        liq_taken_short = h[-1] > swing_high
        recent_low = min(l[-8:-1])
        mss_short = c[-1] < recent_low 

        avg_vol = sum(v[-11:-1]) / 10
        vol_ok = v[-1] > (avg_vol * 1.2)
        
        if vol_ok:
            if liq_taken_long and mss_long:
                return 'buy', c[-1], min(l[-5:]), "LONG_SMC"
            if liq_taken_short and mss_short:
                return 'sell', c[-1], max(h[-5:]), "SHORT_SMC"
        return None, None, None, None
    except: return None, None, None, None

# Telegram diğer komutlar (bakiye, durum)
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance({'type': 'swap'})
        bot.reply_to(message, f"💰 Bakiye: {bal['total'].get('USDT', 0):.2f} USDT")
    except: pass

@bot.message_handler(commands=['durum'])
def send_status(message):
    bot.reply_to(message, f"📡 Bot AKTİF\nTaranan: {len(scanned_list)}\nAktif işlem: {len(active_trades)}")

# Başlat
if __name__ == "__main__":
    ex.load_markets()
    ex.set_position_mode(True)   # Hedge Mode
    threading.Thread(target=report_loop, daemon=True).start()
    threading.Thread(target=main_loop, daemon=True).start()
    bot.infinity_polling()
