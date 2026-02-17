import os, time, telebot, ccxt, threading, re, json
from google import genai

# --- [BAGLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 FLASH: TİCARET DEHASI] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget borsasında bir ticaret dehasısın.
Kullanıcıya samimi davran, fırsat gördüğünde veya istendiğinde şu formatla işlem aç:
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
Risk anlatma, doğrudan aksiyon al!
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

# --- [YENİ MODÜL: OTONOM BEKÇİ - SL & TRAILING STOP] ---
def position_manager():
    """Pozisyonları 15 saniyede bir tarar, kâr koruma ve SL kararlarını otonom verir."""
    highest_points = {} # Her paritenin gördüğü en yüksek ROE'yi tutar
    
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            active_trades = [p for p in pos if float(p.get('contracts', 0)) > 0]

            for p in active_trades:
                sym = p['symbol']
                side = p['side']
                roe = float(p.get('percentage', 0)) # Mevcut Kar/Zarar yüzdesi
                
                # Başlangıç kaydı
                if sym not in highest_points:
                    highest_points[sym] = roe

                # --- 1. STOP LOSS (ZARAR KES) ---
                # Zarar %5'e ulaşırsa acımadan kapat (Deha kuralı: sermayeyi koru)
                if roe <= -5.0:
                    side_to_close = 'sell' if side == 'long' else 'buy'
                    exch.create_market_order(sym, 'market', side_to_close, float(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ **STOP LOSS:** {sym} zarar %5'e ulaştı, sermayeyi korumak için pozisyonu kapattım.")
                    continue

                # --- 2. TRAILING STOP (İZ SÜREN STOP) ---
                # Zirveyi güncelle
                if roe > highest_points[sym]:
                    highest_points[sym] = roe

                # Eğer kâr %3'ü geçtiyse 'İz Sürme' başlar
                if highest_points[sym] >= 3.0:
                    # Zirveden %2.5 geri çekilirse Kârı Al ve Çık
                    if (highest_points[sym] - roe) >= 2.5:
                        side_to_close = 'sell' if side == 'long' else 'buy'
                        exch.create_market_order(sym, 'market', side_to_close, float(p['contracts']), params={'reduceOnly': True})
                        bot.send_message(CHAT_ID, f"💰 **KÂR KİLİTLENDİ:** {sym} zirveden (%{highest_points[sym]:.2f}) geri çekildi. %{roe:.2f} kâr ile ayrıldık.")
                        if sym in highest_points: del highest_prices[sym]

            time.sleep(15) # Scalp hızı
        except Exception as e:
            print(f"Bekçi Hatası: {e}")
            time.sleep(10)

def execute_trade(decision):
    try:
        if "@@[ACTION: TRADE" in decision:
            exch = get_exch()
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                raw_sym, side_raw, lev_raw, amt_raw = match.groups()
                side = 'buy' if any(x in side_raw.upper() for x in ['BUY', 'LONG']) else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', lev_raw)))
                amt = float(re.sub(r'[^0-9.]', '', amt_raw))
                
                exch.load_markets()
                exact_sym = next((s for s in exch.markets if raw_sym.strip().upper() in s and ':USDT' in s), None)
                
                if exact_sym:
                    balance = exch.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 0))
                    final_amt = min(amt, free_usdt * 0.9)
                    if final_amt < 5: return f"⚠️ Bakiye yetersiz."

                    try: exch.set_leverage(lev, exact_sym)
                    except: pass

                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (final_amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        exch.create_market_order(exact_sym, 'market', side, qty)
                        return f"🚀 **İŞLEM BAŞARILI**\n{exact_sym} | {side.upper()} | {lev}x"
        return None
    except Exception as e:
        return f"⚠️ Hata: {str(e)}"

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            active = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:10]
            market_data = "CANLI VERİLER:\n" + "\n".join([f"{x['s']}: %{x['p']}" for x in active])
            
            prompt = f"{market_data}\n\nKullanıcı: '{message.text}'\n\nGemini, analiz et ve aksiyon al."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            bot.reply_to(message, response.split("@@")[0].strip())
            res = execute_trade(response)
            if res: bot.send_message(CHAT_ID, res)
        except Exception as e:
            bot.reply_to(message, f"Hata: {e}")

def autonomous_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            active = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:5]
            summary = ", ".join([f"{x['s']}: %{x['p']}" for x in active])
            prompt = f"Piyasa: {summary}\nDostuna not bırak ve fırsat varsa @@ formatıyla aç."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            if response.strip():
                bot.send_message(CHAT_ID, f"🧠 **RADAR**\n\n{response.split('@@')[0].strip()}")
                execute_trade(response)
            time.sleep(600)
        except: time.sleep(60)

if __name__ == "__main__":
    # 1. Bekçi Modülünü (Trailing Stop) başlat
    threading.Thread(target=position_manager, daemon=True).start()
    # 2. Otonom Analizi başlat
    threading.Thread(target=autonomous_loop, daemon=True).start()
    
    print("Gemini 3 Flash: Hem Avcı Hem Bekçi Başladı!")
    bot.infinity_polling()
