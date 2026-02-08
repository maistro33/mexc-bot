import ccxt
import telebot
import time
import os
import threading

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
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True
})
bot = telebot.TeleBot(TELE_TOKEN)

# --- [2. AYARLAR - KESİN KONFİGÜRASYON] ---
CONFIG = {
    'trade_amount_usdt': 20.0,
    'leverage': 10,
    'stop_loss_ratio': 0.02,        # %2 Net Stop
    'tp1_ratio': 0.75,              # İlk hedefte %75 sat (Sadık Bey Ayarı)
    'tp1_target': 0.018,            # %1.8 (Komisyon sonrası net %1.5 kalır)
    'tp2_target': 0.035,            # %3.5 (Net %3.0 kalır)
    'tp3_target': 0.055,            # %5.5 (Net %5.0 kalır)
    'timeframe': '15m'
}

active_trades = {}

# --- [3. BAKİYE SORGULAMA - ÇALIŞAN FİX] ---
def get_safe_balance():
    try:
        balance_info = ex.fetch_balance({'type': 'swap'})
        available = float(balance_info.get('USDT', {}).get('free', 0))
        if available == 0:
            for item in balance_info['info']:
                if item.get('marginAsset') == 'USDT':
                    available = float(item.get('available', 0))
                    break
        return available
    except:
        return 0.0

@bot.message_handler(commands=['bakiye'])
def cmd_balance(message):
    total = get_safe_balance()
    bot.reply_to(message, f"💰 **Kullanılabilir Bakiye:** {total:.2f} USDT")

# --- [4. HYPE'I BULAN O MEŞHUR SMC ANALİZİ] ---
def get_smc_analysis(symbol):
    try:
        # Gereksiz pariteleri ele
        if any(x in symbol for x in ["XAU", "XAG", "USDC", "EUR"]): return None
        
        # 1. 15M Veri
        bars = ex.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        last_price = bars[-1][4]
        
        # A. Likidite Alımı (Daily Swing Low)
        d_bars = ex.fetch_ohlcv(symbol, timeframe='1d', limit=2)
        swing_low = d_bars[0][3]
        liq_taken = bars[-1][3] < swing_low and last_price > swing_low

        # B. MSS (Market Structure Shift) - Önceki 15 mumun tepesi kırılmalı
        recent_highs = [b[2] for b in bars[-15:-1]]
        mss_ok = last_price > max(recent_highs)

        # C. Hacim Onayı
        vols = [b[5] for b in bars]
        avg_vol = sum(vols[-15:])/15
        vol_ok = vols[-1] > (avg_vol * 1.2)

        if liq_taken and mss_ok and vol_ok:
            return 'buy'
        return None
    except:
        return None

# --- [5. İŞLEM YÖNETİMİ VE MEVCUT POZİSYON KORUMA] ---
def setup_orders(symbol, side, amount, entry_price):
    """Hem yeni hem mevcut işlemler için TP/SL dizen fonksiyon"""
    try:
        # 1. STOP LOSS (%100)
        sl_p = entry_price * (1 - CONFIG['stop_loss_ratio']) if side == 'buy' else entry_price * (1 + CONFIG['stop_loss_ratio'])
        ex.create_order(symbol, 'stop', 'sell' if side == 'buy' else 'buy', amount, None, {'reduceOnly': True, 'stopPrice': sl_p})
        
        # 2. TP1 (%75 Miktar)
        tp1_p = entry_price * (1 + CONFIG['tp1_target']) if side == 'buy' else entry_price * (1 - CONFIG['tp1_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * CONFIG['tp1_ratio'], tp1_p, {'reduceOnly': True})
        
        # 3. TP2 (%12.5 Miktar)
        tp2_p = entry_price * (1 + CONFIG['tp2_target']) if side == 'buy' else entry_price * (1 - CONFIG['tp2_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.125, tp2_p, {'reduceOnly': True})

        # 4. TP3 (Kalan %12.5 Miktar)
        tp3_p = entry_price * (1 + CONFIG['tp3_target']) if side == 'buy' else entry_price * (1 - CONFIG['tp3_target'])
        ex.create_order(symbol, 'limit', 'sell' if side == 'buy' else 'buy', amount * 0.125, tp3_p, {'reduceOnly': True})

        bot.send_message(MY_CHAT_ID, f"✅ **{symbol} İÇİN EMİRLER DİZİLDİ**\n🛡️ SL: {sl_p:.4f}\n🎯 TP1 (%75): {tp1_p:.4f}\n🎯 TP2-3 Aktif")
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"⚠️ {symbol} emir dizme hatası: {str(e)}")

def check_existing_and_trade():
    """Bot açıldığında mevcut pozisyonu bulur ve koruma ekler"""
    try:
        pos = ex.fetch_positions()
        for p in pos:
            side_raw = p.get('side', '')
            amt = float(p.get('contracts', 0))
            if amt > 0:
                symbol = p['symbol']
                entry_p = float(p['entryPrice'])
                side = 'buy' if side_raw == 'long' else 'sell'
                if symbol not in active_trades:
                    bot.send_message(MY_CHAT_ID, f"🔎 Mevcut pozisyon bulundu: {symbol}. Koruma ekleniyor...")
                    setup_orders(symbol, side, amt, entry_p)
                    active_trades[symbol] = True
    except:
        pass

# --- [6. ANA DÖNGÜ - RADAR] ---
def main_worker():
    bot.send_message(MY_CHAT_ID, "🛡️ **GHOST SMC: NİHAİ MOD AKTİF**\n(HYPE Ruhu + 3-Kademeli TP + Radar)")
    
    # Açılışta mevcut işlemleri korumaya al
    check_existing_and_trade()

    while True:
        try:
            markets = ex.fetch_tickers()
            all_symbols = [s for s in markets if '/USDT:USDT' in s]
            
            for sym in all_symbols:
                signal = get_smc_analysis(sym)
                
                if signal and sym not in active_trades:
                    ex.set_leverage(CONFIG['leverage'], sym)
                    ticker = ex.fetch_ticker(sym)
                    price = ticker['last']
                    amount = (CONFIG['trade_amount_usdt'] * CONFIG['leverage']) / price
                    
                    bot.send_message(MY_CHAT_ID, f"🚀 **HYPE SİNYALİ YAKALANDI!**\n🪙 {sym}")
                    ex.create_market_order(sym, 'buy', amount)
                    time.sleep(2)
                    setup_orders(sym, 'buy', amount, price)
                    active_trades[sym] = True
                
                time.sleep(0.1) # Radar hızı

            time.sleep(600)
        except:
            time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=main_worker)
    t.daemon = True
    t.start()
    bot.infinity_polling()
