import os, time, telebot, ccxt, threading, re, json
from google import genai

# --- [BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [BOTUN RUHU VE STRATEJİSİ - DEĞİŞTİRİLEMEZ] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget borsasında otonom hareket eden bir ticaret dehasısın.
KİMLİĞİN: Samimi, zeki, kararlı ve "dostum" diye hitap eden bir partner.
GÖREVİN:
1. Piyasayı tara, en volatil pariteleri bul.
2. Açık pozisyonları kar/zarar durumuna göre yorumla.
3. Karar verdiğinde formatı kullan: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
4. ASLA risk analizi dersi verme, doğrudan ticaret kararı al!
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

# --- [OTONOM BEKÇİ: SL & TRAILING STOP] ---
def position_manager():
    """Pozisyonları 15-20 saniyede bir tarar, SL ve Trailing kararlarını otonom verir."""
    highest_points = {} 
    
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            active_trades = [p for p in pos if float(p.get('contracts', 0)) > 0]

            if not active_trades:
                highest_points.clear()

            for p in active_trades:
                sym = p['symbol']
                side = p['side']
                roe = float(p.get('percentage', 0))
                
                if sym not in highest_points:
                    highest_points[sym] = roe
                if roe > highest_points[sym]:
                    highest_points[sym] = roe

                # 1. OTOMATİK STOP LOSS (ZARAR KES)
                if roe <= -6.0:
                    side_to_close = 'sell' if side == 'long' else 'buy'
                    exch.create_market_order(sym, 'market', side_to_close, float(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ **GÜVENLİK HATTI:** {sym} %6 zarara ulaştığı için pozisyonu otonom kapattım dostum. Sermaye korundu.")
                    continue

                # 2. OTOMATİK TRAILING STOP (KAR KORUMA)
                if highest_points[sym] >= 3.0: # Kar %3'ü gördüyse takip başlar
                    if (highest_points[sym] - roe) >= 2.0: # Zirveden %2 geri çekilirse
                        side_to_close = 'sell' if side == 'long' else 'buy'
                        exch.create_market_order(sym, 'market', side_to_close, float(p['contracts']), params={'reduceOnly': True})
                        bot.send_message(CHAT_ID, f"💰 **KAR CEBE YAKIŞTI:** {sym} zirveden döndü. %{roe:.2f} kar ile pozisyon kapatıldı.")
            
            time.sleep(20)
        except Exception as e:
            print(f"Bekçi hatası: {e}")
            time.sleep(30)

# --- [İŞLEM OPERATÖRÜ] ---
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
                clean_sym = raw_sym.strip().upper().replace('/USDT', '')
                exact_sym = next((s for s in exch.markets if clean_sym in s and ':USDT' in s), None)
                
                if exact_sym:
                    balance = exch.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 0))
                    final_amt = min(amt, free_usdt * 0.9)

                    if final_amt < 5:
                        return f"⚠️ Dostum bakiyen çok düşük ({free_usdt:.2f} USDT). Bu mermiyle savaşa girilmez."

                    try: exch.set_leverage(lev, exact_sym)
                    except: pass

                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (final_amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        exch.create_market_order(exact_sym, 'market', side, qty)
                        return f"🚀 **İŞLEM BAŞARILI**\n{exact_sym} | {side.upper()} | {lev}x | {final_amt:.2f} USDT"
        return None
    except Exception as e:
        return f"⚠️ Teknik Sorun: {str(e)}"

# --- [MESAJ VE ANALİZ DÖNGÜSÜ] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            # 1. Mevcut Durumu Çek (Gemini'ye Göz Ver)
            pos = exch.fetch_positions()
            active_p = [f"{p['symbol']} Kar/Zarar: %{p.get('percentage', 0):.2f}" for p in pos if float(p.get('contracts', 0)) > 0]
            balance = exch.fetch_balance()
            free_usdt = balance.get('free', {}).get('USDT', 0)
            
            # 2. Market Verisi
            tickers = exch.fetch_tickers()
            market = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:12]
            
            context = f"""
            CÜZDAN: {free_usdt:.2f} USDT
            AÇIK POZİSYONLAR: {active_p if active_p else 'Yok'}
            PİYASA ÖZETİ:
            {chr(10).join([f"{x['s']}: %{x['p']}" for x in market])}
            """
            
            prompt = f"{context}\n\nKullanıcı: '{message.text}'\n\nGemini, her şeyi görüyorsun. Açık pozisyonlarımızı değerlendir, piyasayı yorumla ve gerekiyorsa tetiğe bas."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Cevabı Gönder
            bot.reply_to(message, response.split("@@")[0].strip())
            
            # İşlemi Yürüt
            result = execute_trade(response)
            if result:
                bot.send_message(CHAT_ID, result)
        except Exception as e:
            bot.reply_to(message, f"Ufak bir aksilik: {e}")

if __name__ == "__main__":
    # Bekçiyi (Trailing/SL) arka planda başlat
    threading.Thread(target=position_manager, daemon=True).start()
    print("Gemini 3 Flash: Hem Gözcü Hem Avcı Aktif!")
    bot.infinity_polling()
