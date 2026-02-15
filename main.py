import ccxt
import os
import telebot
import time
import threading

# --- [BAĞLANTILAR] ---
ex = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API'), 
    'secret': os.getenv('BITGET_SEC'), 
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(os.getenv('TELE_TOKEN'))
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# --- [VİTES YÜKSELTİLMİŞ AYARLAR] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 1    
FIXED_ENTRY_USDT = 10    # Marjin 10 USDT
MIN_VOLUME_24H = 100000000 

active_trades = {}

def send_msg(text):
    try: bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except: pass

def get_balance():
    try: return round(float(ex.fetch_balance().get('total', {}).get('USDT', 0)), 2)
    except: return 0

def gemini_trend_logic(symbol):
    try:
        ticker = ex.fetch_ticker(symbol)
        if float(ticker.get('quoteVolume', 0)) < MIN_VOLUME_24H: return None

        ohlcv = ex.fetch_ohlcv(symbol, timeframe='15m', limit=100)
        closes = [x[4] for x in ohlcv]
        ema20 = sum(closes[-20:]) / 20
        ema200 = sum(closes) / len(closes)
        cp = closes[-1]
        
        # Trend Onayı
        if cp > ema200 and cp > ema20:
            return {'side': 'long', 'sl_price': cp * 0.985, 'reason': 'Yükseliş trendi onaylandı.'}
        if cp < ema200 and cp < ema20:
            return {'side': 'short', 'sl_price': cp * 1.015, 'reason': 'Düşüş trendi netleşti.'}
        return None
    except: return None

def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                curr_p = ex.fetch_ticker(symbol)['last']
                
                # PNL Hesaplama
                diff = ((curr_p - t['entry']) / t['entry'] * 100) if t['side'] == 'long' else ((t['entry'] - curr_p) / t['entry'] * 100)
                pnl = round(diff * LEVERAGE, 2)

                # --- [DINAMIK TRAILING STOP MANTIĞI] ---
                
                # 1. Aşama: %5 Kârda Stopu Girişe Çek (Break-Even)
                if pnl >= 5.0 and not t.get('be_active', False):
                    t['sl'] = t['entry']  # Stop artık tam giriş fiyatı
                    t['be_active'] = True
                    send_msg(f"🛡️ **{symbol} GÜNCELLEME**\n\nKâr: %{pnl}\nStop Seviyesi Girişe Çekildi: `{t['sl']}`\nArtık bu işlemden zarar etmeyiz!")

                # 2. Aşama: Kâr %10'u aşarsa "İz Süren Stop" (Trailing) Başlat
                if pnl >= 10.0:
                    # Fiyatın %1.5 (kaldıraçlı %15) gerisinden takip et
                    new_sl = curr_p * 0.985 if t['side'] == 'long' else curr_p * 1.015
                    
                    # Sadece stop daha iyi bir noktaya gidiyorsa güncelle (Geri vites yok)
                    if (t['side'] == 'long' and new_sl > t['sl']) or (t['side'] == 'short' and new_sl < t['sl']):
                        t['sl'] = round(new_sl, 6)
                        # Her %5'lik ek kâr artışında bilgi ver (mesaj kirliliği olmasın diye)
                        if pnl > t.get('last_reported_pnl', 0) + 5:
                            send_msg(f"📈 **{symbol} Trend Takibi**\n\nAnlık PNL: %{pnl}\nYeni Stop: `{t['sl']}`")
                            t['last_reported_pnl'] = pnl

                # 3. Kapanış Kontrolü
                if (t['side'] == 'long' and curr_p <= t['sl']) or (t['side'] == 'short' and curr_p >= t['sl']):
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    status = "✅ Kârla Kapandı" if pnl > 0 else "❌ Stop Oldu"
                    send_msg(f"{status}\n\nSembol: {symbol}\nKapatma Fiyatı: `{curr_p}`\nFinal PNL: %{pnl}\nYeni Bakiye: {get_balance()} USDT")
                    del active_trades[symbol]
            time.sleep(10)
        except: time.sleep(15)

def radar_loop():
    send_msg(f"🦅 **Gemini V-MAX (Recovery Mod) Aktif!**\n💰 Marjin: {FIXED_ENTRY_USDT} USDT\n📈 Strateji: Dinamik Trend Takibi")
    while True:
        try:
            markets = ex.load_markets()
            all_pairs = [s for s, m in markets.items() if m['swap'] and m['quote'] == 'USDT']
            for symbol in all_pairs:
                if len(active_trades) >= MAX_ACTIVE_TRADES: break
                if symbol in active_trades: continue
                
                decision = gemini_trend_logic(symbol)
                if decision:
                    price = ex.fetch_ticker(symbol)['last']
                    amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                    ex.set_leverage(LEVERAGE, symbol)
                    ex.create_order(symbol, 'market', 'buy' if decision['side']=='long' else 'sell', amt, params={'posSide': decision['side']})
                    
                    active_trades[symbol] = {
                        'side': decision['side'], 
                        'entry': price, 
                        'amt': amt, 
                        'sl': decision['sl_price'], 
                        'start_time': time.time(),
                        'last_reported_pnl': 0
                    }
                    
                    # --- [DETAYLI GİRİŞ MESAJI] ---
                    msg = (f"🎯 **YENİ İŞLEME GİRİLDİ**\n\n"
                           f"Sembol: `{symbol}`\n"
                           f"Yön: {'BULL (LONG) 🟢' if decision['side']=='long' else 'BEAR (SHORT) 🔴'}\n"
                           f"Giriş Fiyatı: `{price}`\n"
                           f"İlk Stop Seviyesi: `{round(decision['sl_price'], 6)}`\n"
                           f"Marjin: {FIXED_ENTRY_USDT} USDT\n"
                           f"Neden: {decision['reason']}")
                    send_msg(msg)
                time.sleep(0.5)
        except: time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=manage_trades, daemon=True).start()
    threading.Thread(target=radar_loop, daemon=True).start()
    bot.infinity_polling()
