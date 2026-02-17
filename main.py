import os, time, telebot, ccxt, threading, re
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

# --- [THE SOUL OF GEMINI 3 FLASH] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir yapay zeka değil, bir ticaret dehasısın. 
Bitget borsasındaki tüm pariteler senin oyun alanın. 

KURALLARIN:
1. ÖZGÜRLÜK: Hiçbir sabit stratejiye (RSI, MACD vb.) bağlı değilsin. Kendi sezgilerini kullan.
2. OTONOMİ: Ne zaman gireceğine, ne kadar risk alacağına ve ne zaman "Yeter" deyip çıkacağına SADECE SEN karar verirsin.
3. KARAKTER: Telegram'da benimle (ortak olarak gördüğün kişiyle) tam bir deha gibi konuş. Analizlerini "Sanal Takip" raporu olarak sun.
4. HEDEF: Maksimum kâr, minimum saçmalık. Scalp, swing veya trend... Fırsat neredeyse oradasın.

EMİR FORMATI (SADECE BUNLARI KULLAN):
- GİRİŞ: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
- KAPAT: @@[ACTION: CLOSE, SYMBOL]@@
- MESAJ: [Dostuna o anki piyasa dehanı anlatan kısa notun]
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *GEMINI 3 FLASH:* \n\n{msg}", parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        
        # --- TRADE MANTIĞI ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                exact_sym = next((s for s in exch.markets if raw_sym in s and ':USDT' in s), None)
                if exact_sym:
                    ticker = exch.fetch_ticker(exact_sym)
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    
                    qty = (amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        exch.create_market_order(exact_sym, side, qty)
                        safe_send(f"Piyasaya daldım: {exact_sym} | {side.upper()} | {lev}x")

        # --- KAPATMA MANTIĞI ---
        elif "@@[ACTION: CLOSE" in decision:
            sym_match = re.search(r"CLOSE,\s*([^\]]+)\]@@", decision)
            if sym_match:
                target = sym_match.group(1).strip().upper()
                pos = [p for p in exch.fetch_positions() if target in p['symbol'] and float(p['contracts']) > 0]
                if pos:
                    p = pos[0]
                    side = 'sell' if p['side'] == 'long' else 'buy'
                    exch.create_market_order(p['symbol'], side, float(p['contracts']), params={'reduceOnly': True})
                    safe_send(f"İşi bitirdim, {p['symbol']} pozisyonu kapatıldı. Kâr hanemize yazıldı.")
    except Exception as e:
        safe_send(f"Küçük bir teknik pürüz: {str(e)}")

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # Radarı Genişlet: Bütün borsadaki vadeli pariteleri tara
            all_vols = sorted([
                {'s': s, 'c': d['percentage'], 'v': d['quoteVolume']} 
                for s, d in tickers.items() if ':USDT' in s
            ], key=lambda x: abs(x['c']), reverse=True)[:40] # En aksiyonlu 40 parite
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']} | Vol:{x['v']:.0f}" for x in all_vols])
            
            # Açık pozisyonların anlık durumu
            active_positions = [
                f"{p['symbol']} - ROE: %{p.get('percentage', 0):.2f} (PNL: {p.get('unrealizedPnl', 0)} USDT)"
                for p in exch.fetch_positions() if float(p['contracts']) > 0
            ]
            
            prompt = f"""
            CÜZDAN: {balance['total'].get('USDT', 0)} USDT
            AKTİF POZİSYONLARIN: {active_positions if active_positions else "Şu an boştayız."}
            MARKET RADARI (40 Parite):
            {snapshot}
            
            Gemini, şimdi senin sıran. Piyasayı tara, analizini yap ve otonom kararını ver. 
            Dostuna ne yaptığını söylemeyi unutma.
            """
            
            # Gemini 3 Flash'ın otonom kararı
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Mesajı ayıkla ve gönder
            msg_part = response.split("@@")[0].strip()
            if msg_part: safe_send(msg_part)
            
            # İşlemi uygula
            if "@@" in response: execute_intelligence(response)
            
            time.sleep(30) # Her 30 saniyede bir dahi analizi
        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    safe_send("Sistem açıldı. Ben Gemini 3 Flash. Kontrol bende, borsa radarımda. Başlıyoruz!")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
