import ccxt
import os
import telebot
import time
import threading

# --- [BAĞLANTILAR] ---
# Railway veya Terminal üzerinden ortam değişkenlerini (Environment Variables) okur.
ex = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API'), 
    'secret': os.getenv('BITGET_SEC'), 
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {'defaultType': 'swap'}, 
    'enableRateLimit': True
})
bot = telebot.TeleBot(os.getenv('TELE_TOKEN'))
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

# --- [STRATEJİK AYARLAR - KASA KORUMA ODAKLI] ---
LEVERAGE = 10           
MAX_ACTIVE_TRADES = 3    # 34 USDT kasa için ideal (Sadece en iyi 3 fırsat)
FIXED_ENTRY_USDT = 10    # Her işleme 10 USDT bakiye ile giriş
TRAIL_ACTIVATE_PNL = 1.2 # %1.2 kârda takip başlar
TRAIL_DISTANCE = 0.008   # %0.8 geriden izler
MIN_DISPLACEMENT = 0.005 # %0.5 ve üzeri sert mumlar (Gerçek SMC dönüşü)

# İşlemlerin anlık takibi için hafıza
active_trades = {}

# --- [YARDIMCI FONKSİYONLAR] ---
def send_msg(text):
    """Telegram üzerinden rapor verir."""
    try: 
        bot.send_message(MY_CHAT_ID, text, parse_mode='Markdown')
    except Exception as e:
        print(f"Telegram Hatası: {e}")

def get_total_balance():
    """Borsadaki toplam USDT bakiyesini çeker."""
    try:
        bal = ex.fetch_balance()
        return float(bal['total']['USDT'])
    except: 
        return 0.0

# --- [TELEGRAM KOMUT DİNLEYİCİ] ---
@bot.message_handler(commands=['bakiye', 'durum', 'status'])
def send_status(message):
    try:
        current_bal = get_total_balance()
        status_text = f"💰 **KESKİN NİŞANCI RAPORU**\n\n"
        status_text += f"💵 **Toplam Kasa:** {round(current_bal, 2)} USDT\n"
        status_text += f"📊 **Aktif Avlar:** {len(active_trades)}/{MAX_ACTIVE_TRADES}\n"
        status_text += "━━━━━━━━━━━━━━\n"
        
        if active_trades:
            for sym, t in active_trades.items():
                pnl_val = t.get('pnl', 0)
                icon = "🟢" if pnl_val > 0 else "🔴"
                status_text += f"{icon} **{sym}**\n"
                status_text += f"   - Yön: {t['side'].upper()}\n"
                status_text += f"   - PNL: %{pnl_val}\n"
                status_text += f"   - Kalkan: {'🛡️ AKTİF' if t.get('be_active') else '⏳ BEKLENİYOR'}\n\n"
        else:
            status_text += "😴 Radar temiz, yeni av bekleniyor."
            
        bot.reply_to(message, status_text, parse_mode='Markdown')
    except:
        bot.reply_to(message, "⚠️ Rapor hazırlanırken bir hata oluştu.")

# --- [SMC ANALİZ MOTORU] ---
def check_smc_signal(symbol):
    try:
        ohlcv = ex.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        # Likidite alanı taraması (Son 40 mum)
        lookback = ohlcv[-45:-5]
        max_h = max([x[2] for x in lookback])
        min_l = min([x[3] for x in lookback])
        
        m3, m2, m1 = ohlcv[-3], ohlcv[-2], ohlcv[-1]
        move_size = abs(m1[4] - m1[1]) / m1[1]

        # LONG (Alış) Onayı: Likidite Alımı + Sert Dönüş + FVG
        if m2[3] < min_l and m1[4] > m2[2] and move_size >= MIN_DISPLACEMENT:
            if m1[3] > m3[2]:
                return {'side': 'long', 'entry': (m1[3] + m3[2]) / 2, 'sl': m2[3]}
        
        # SHORT (Satış) Onayı
        if m2[2] > max_h and m1[4] < m2[3] and move_size >= MIN_DISPLACEMENT:
            if m1[2] < m3[3]:
                return {'side': 'short', 'entry': (m1[2] + m3[3]) / 2, 'sl': m2[2]}
        return None
    except: return None

# --- [SANAL TAKİP VE İŞLEM YÖNETİMİ] ---
def manage_trades():
    global active_trades
    while True:
        try:
            for symbol in list(active_trades.keys()):
                t = active_trades[symbol]
                ticker = ex.fetch_ticker(symbol)
                curr_p = ticker['last']
                
                # PNL Hesaplama
                pnl = round(((curr_p - t['entry']) if t['side'] == 'long' else (t['entry'] - curr_p)) / t['entry'] * 100 * LEVERAGE, 2)
                active_trades[symbol]['pnl'] = pnl 

                # 🛡️ KOMİSYON KALKANI (BE+)
                # PNL %0.8 olunca masrafları kurtaracak şekilde stopu girişe çek.
                if pnl >= 0.8 and not t.get('be_active', False):
                    offset = 0.002 # %0.2 kâr payı ekle
                    active_trades[symbol]['sl'] = t['entry'] * (1 + offset) if t['side'] == 'long' else t['entry'] * (1 - offset)
                    active_trades[symbol]['be_active'] = True
                    send_msg(f"🛡️ **{symbol} Korumaya Alındı.**\nKâr %0.8'e ulaştı, stop girişe (BE+) çekildi. Zarar ihtimali sıfırlandı.")

                # 🏃 İZ SÜREN STOP (TRAILING)
                if pnl >= TRAIL_ACTIVATE_PNL:
                    potential_sl = curr_p * (1 - TRAIL_DISTANCE) if t['side'] == 'long' else curr_p * (1 + TRAIL_DISTANCE)
                    is_better = potential_sl > t['sl'] if t['side'] == 'long' else potential_sl < t['sl']
                    if is_better:
                        active_trades[symbol]['sl'] = potential_sl
                        active_trades[symbol]['trailing_active'] = True

                # 🏁 KAPANIŞ KONTROLÜ
                hit_sl = (curr_p <= t['sl']) if t['side'] == 'long' else (curr_p >= t['sl'])
                if hit_sl:
                    ex.create_order(symbol, 'market', 'sell' if t['side'] == 'long' else 'buy', t['amt'], params={'posSide': t['side'], 'reduceOnly': True})
                    
                    final_bal = get_total_balance()
                    msg = "✅ **KÂRLI TAKİP SONLANDI**" if t.get('trailing_active') else "🛡️ **KORUMALI KAPANIŞ**"
                    if pnl < 0 and not t.get('be_active'): msg = "🛑 **STOP OLDU**"
                    
                    send_msg(f"{msg}\n**Coin:** {symbol}\n**Final PNL:** %{pnl}\n**Yeni Bakiye:** {round(final_bal, 2)} USDT\nKasa süpürüldü. ✅")
                    del active_trades[symbol]
            time.sleep(6)
        except: time.sleep(10)

# --- [RADAR DÖNGÜSÜ] ---
def radar_loop():
    send_msg("🦅 **KESKİN NİŞANCI RADARI AKTİF!**\nSadece sert hacimli SMC dönüşleri taranıyor.\n`/bakiye` yazarak beni kontrol edebilirsin.")
    while True:
        try:
            if len(active_trades) < MAX_ACTIVE_TRADES:
                tickers = ex.fetch_tickers()
                # En yüksek hacimli 100 coin (SMC için en güvenli alan)
                pairs = sorted([s for s in tickers if '/USDT:USDT' in s], key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:100]
                
                for symbol in pairs:
                    if len(active_trades) >= MAX_ACTIVE_TRADES: break
                    if symbol in active_trades: continue
                    
                    sig = check_smc_signal(symbol)
                    if sig:
                        # Bakiye kontrolü (Minimum 10 USDT serbest bakiye lazım)
                        bal = ex.fetch_balance()
                        if float(bal['free']['USDT']) < FIXED_ENTRY_USDT: continue 
                        
                        try:
                            price = ex.fetch_ticker(symbol)['last']
                            amt = (FIXED_ENTRY_USDT * LEVERAGE) / price
                            
                            ex.set_leverage(LEVERAGE, symbol)
                            ex.create_order(symbol, 'market', 'buy' if sig['side']=='long' else 'sell', amt, params={'posSide': sig['side']})
                            
                            active_trades[symbol] = {
                                'side': sig['side'], 'entry': price, 'amt': amt, 
                                'sl': sig['sl'], 'trailing_active': False, 'be_active': False, 'pnl': 0
                            }
                            send_msg(f"🏹 **YENİ AV YAKALANDI!**\n\n**Coin:** {symbol}\n**Yön:** {sig['side'].upper()}\n**Miktar:** 10 USDT\n🛡️ **İlk SL:** {round(sig['sl'], 5)}")
                            time.sleep(2)
                        except: pass
            time.sleep(15)
        except: time.sleep(30)

# --- [ANA ÇALIŞTIRICI] ---
if __name__ == "__main__":
    # 1. Telegram Komutlarını Dinle (Arka Planda)
    threading.Thread(target=lambda: bot.infinity_polling()).start()
    # 2. İşlemleri Yönet (Arka Planda)
    threading.Thread(target=manage_trades).start()
    # 3. Radar Tarayıcıyı Başlat (Ana Dizinde)
    radar_loop()
