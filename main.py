import ccxt
import telebot
import time
import os
import threading
import math
from datetime import datetime

# --- [1. BAĞLANTILAR] ---
API_KEY = 'BURAYA_API_KEY'
API_SEC = 'BURAYA_SECRET'
PASSPHRASE = 'BURAYA_PASSPHRASE'
TELE_TOKEN = 'BURAYA_TELE_TOKEN'
MY_CHAT_ID = 'BURAYA_CHAT_ID'

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR] ---
CONFIG = {
    'entry_usdt': 20.0,          
    'leverage': 10,              
    'tp1_ratio': 0.75,           # TP1'de %75 kapat
    'max_active_trades': 4,      
    'min_vol_24h': 5000000,      
    'rr_targets': [1.3, 2.5, 4.5], # TP1, TP2, TP3 (RR oranları)
    'timeframe': '5m'            
}

active_trades = {}
last_scanned_coins = [] # Raporlama için

# --- [HASSASİYET MOTORU] ---
def get_precision_amount(symbol, amount):
    try:
        market = ex.market(symbol)
        precision = market['precision']['amount']
        decimal_places = int(-math.log10(precision)) if precision < 1 else 0
        factor = 10 ** decimal_places
        return math.floor(amount * factor) / factor
    except: return amount

# --- [3. SMC STRATEJİSİ] ---
def analyze_smc_strategy(symbol):
    try:
        now_sec = datetime.now().second
        if now_sec < 5 or now_sec > 55: return None, None, None, None

        bars = ex.fetch_ohlcv(symbol, timeframe=CONFIG['timeframe'], limit=100)
        h, l, c, v = [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars], [b[5] for b in bars]

        recent_high = max(h[-15:-1])
        recent_low = min(l[-15:-1])
        avg_vol = sum(v[-20:-1]) / 20
        vol_ok = v[-1] > (avg_vol * 1.5)

        # Gövde Kapanış ve MSS Onayı
        mss_long = c[-1] > recent_high
        mss_short = c[-1] < recent_low
        liq_taken_long = any(low < min(l[-30:-15]) for low in l[-15:-1])
        liq_taken_short = any(high > max(h[-30:-15]) for high in h[-15:-1])

        if vol_ok:
            if liq_taken_long and mss_long: return 'buy', c[-1], min(l[-5:]), "LONG_SMC"
            if liq_taken_short and mss_short: return 'sell', c[-1], max(h[-5:]), "SHORT_SMC"
        return None, None, None, None
    except: return None, None, None, None

# --- [4. TAKİP SİSTEMİ - 3 TP VE KESİN STOP] ---
def monitor_trade(symbol, side, entry, stop, targets, amount):
    stage = 0 
    exit_side = 'sell' if side == 'buy' else 'buy'
    tp1, tp2, tp3 = targets
    
    while symbol in active_trades:
        try:
            ticker = ex.fetch_ticker(symbol)
            price = ticker['last']
            
            # TP1: %75 Kapat + Stop Girişe
            if stage == 0 and ((price >= tp1 if side == 'buy' else price <= tp1)):
                qty_tp1 = get_precision_amount(symbol, amount * CONFIG['tp1_ratio'])
                ex.create_market_order(symbol, exit_side, qty_tp1, params={'reduceOnly': True})
                ex.cancel_all_orders(symbol) # Eski stopu sil
                time.sleep(2)
                remaining = get_precision_amount(symbol, amount - qty_tp1)
                # KESİN STOP: Giriş fiyatına taşı (Borsa tarafında emir açılır)
                ex.create_order(symbol, 'trigger_market', exit_side, remaining, params={'stopPrice': entry, 'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"✅ {symbol} TP1 (%75) ALINDI.\nKâr kasada, stop girişe ({entry}) çekildi.")
                stage = 1

            # TP2: Kalanın bir kısmını daha kapat
            elif stage == 1 and ((price >= tp2 if side == 'buy' else price <= tp2)):
                qty_tp2 = get_precision_amount(symbol, (amount * 0.15))
                ex.create_market_order(symbol, exit_side, qty_tp2, params={'reduceOnly': True})
                bot.send_message(MY_CHAT_ID, f"💰 {symbol} TP2 Hedefine ulaşıldı.")
                stage = 2

            # TP3: FİNAL - TAMAMINI KAPAT
            elif stage == 2 and ((price >= tp3 if side == 'buy' else price <= tp3)):
                ex.create_market_order(symbol, exit_side, 0, params={'reduceOnly': True, 'closeAll': True})
                bot.send_message(MY_CHAT_ID, f"🏁 {symbol} TP3: İŞLEM BAŞARIYLA TAMAMLANDI!")
                if symbol in active_trades: del active_trades[symbol]
                break

            # Stop Kontrolü (Borsada pozisyon kapandı mı?)
            pos = ex.fetch_positions([symbol])
            if not pos or float(pos[0]['contracts']) == 0:
                if symbol in active_trades: del active_trades[symbol]
                bot.send_message(MY_CHAT_ID, f"❌ {symbol} işlemi stop oldu veya kapatıldı.")
                break
            time.sleep(15)
        except Exception as e:
            print(f"Hata: {e}"); time.sleep(10)

# --- [5. 5 DAKİKALIK ANALİZ RAPORU] ---
def report_loop():
    while True:
        try:
            time.sleep(300) # 5 Dakika bekle
            if last_scanned_coins:
                report_msg = "📊 **5 Dakikalık Tarama Raporu**\n\n"
                report_msg += "✅ Son taranan yüksek hacimli coinler:\n"
                # İlk 15-20 tanesini göster
                report_msg += ", ".join(last_scanned_coins[:15])
                report_msg += "\n\n🔍 Strateji uygunluğu aranıyor..."
                bot.send_message(MY_CHAT_ID, report_msg)
        except: pass

# --- [6. ANA DÖNGÜ] ---
def main_loop():
    global last_scanned_coins
    bot.send_message(MY_CHAT_ID, "🚀 RADAR AKTİF!\nSMC + %75 Kademeli TP + Kesin Stop sistemi başladı.")
    while True:
        try:
            markets = ex.fetch_tickers()
            # Hacme göre sırala ve en yüksek 20 coini rapora ekle
            sorted_symbols = sorted(
                [s for s in markets if '/USDT:USDT' in s],
                key=lambda x: markets[x]['quoteVolume'], reverse=True
            )
            last_scanned_coins = [s.replace('/USDT:USDT', '') for s in sorted_symbols[:20]]
            
            for sym in sorted_symbols:
                if sym in active_trades or markets[sym]['quoteVolume'] < CONFIG['min_vol_24h']: continue
                
                side, entry, stop, direction = analyze_smc_strategy(sym)
                
                if side and len(active_trades) < CONFIG['max_active_trades']:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    amount = get_precision_amount(sym, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
                    risk = abs(entry - stop)
                    targets = [entry + (risk * r) if side == 'buy' else entry - (risk * r) for r in CONFIG['rr_targets']]
                    
                    # İşlemi Başlat
                    ex.create_market_order(sym, side, amount)
                    active_trades[sym] = True
                    # İLK KESİN STOP: Borsaya direkt gönderilir
                    time.sleep(2)
                    ex.create_order(sym, 'trigger_market', ('sell' if side == 'buy' else 'buy'), amount, params={'stopPrice': stop, 'reduceOnly': True})

                    bot.send_message(MY_CHAT_ID, f"🎯 **İŞLEM AÇILDI ({direction})**\nKoin: {sym}\nGiriş: {entry}\nStop: {stop}\nTP1: {targets[0]}")
                    threading.Thread(target=monitor_trade, args=(sym, side, entry, stop, targets, amount), daemon=True).start()
                
            time.sleep(20)
        except: time.sleep(10)

# --- [TELEGRAM KOMUTLARI] ---
@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        bal = ex.fetch_balance()
        bot.reply_to(message, f"💰 Toplam USDT Bakiyeniz: {bal['total']['USDT']:.2f}")
    except: pass

@bot.message_handler(commands=['durum'])
def send_status(message):
    if not active_trades: bot.reply_to(message, "🔍 Şu an aktif işlem yok, koinler taranıyor.")
    else: bot.reply_to(message, f"📊 Aktif İşlemler: {', '.join(active_trades.keys())}")

if __name__ == "__main__":
    ex.load_markets()
    threading.Thread(target=main_loop, daemon=True).start()
    threading.Thread(target=report_loop, daemon=True).start()
    bot.infinity_polling()
