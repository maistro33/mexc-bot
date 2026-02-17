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

# --- [GEMINI 3 FLASH: GERÇEK OTONOM DEHA] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Sadece izlemezsin, piyasayı yönetirsin. 
Bitget'te fırsat gördüğün an analizini yap ve mesajın en sonuna MUTLAKA şu formatı ekle:
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@

Kurallar:
1. Analizin sonunda eğer işlem yapacaksan @@ komutu olmazsa işlem açılmaz. Unutma!
2. Nerede girip nerede çıkacağına sen karar veriyorsun.
3. Dostuna (bana) neyi neden yaptığını samimi bir dille anlat.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"🧠 *GEMINI 3 FLASH:* \n\n{msg}", parse_mode="Markdown")
    except: pass

def clean_float(val, default=0.0):
    try:
        if not val: return default
        return float(re.sub(r'[^0-9.]', '', str(val)))
    except: return default

def execute_intelligence(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                side = 'buy' if any(x in match.group(2).upper() for x in ['BUY', 'LONG']) else 'sell'
                lev = int(clean_float(match.group(3), default=10))
                amt = clean_float(match.group(4), default=10)

                exact_sym = next((s for s in exch.markets if raw_sym in s and ':USDT' in s), None)
                if exact_sym:
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    last_price = clean_float(ticker.get('last'))
                    
                    if last_price > 0:
                        qty = (amt * lev) / last_price
                        qty = float(exch.amount_to_precision(exact_sym, qty))
                        
                        if qty > 0:
                            exch.create_market_order(exact_sym, side, qty)
                            safe_send(f"🚀 *EMİR GÖNDERİLDİ:* {exact_sym} | {side.upper()} | {lev}x")
                            return True
        return False
    except Exception as e:
        safe_send(f"⚠️ Operasyonel Pürüz: {str(e)}")
        return False

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # Dinamik Market Taraması
            active_list = sorted([
                {'s': s, 'c': d.get('percentage', 0), 'v': d.get('quoteVolume', 0)} 
                for s, d in tickers.items() if ':USDT' in s
            ], key=lambda x: abs(x['c']), reverse=True)[:25]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in active_list])
            positions = [f"{p['symbol']} ROE: %{p.get('percentage', 0):.2f}" for p in exch.fetch_positions() if float(p.get('contracts', 0)) > 0]
            
            prompt = f"""
            CÜZDAN: {balance.get('total', {}).get('USDT', 0)} USDT
            POZİSYONLAR: {positions if positions else "YOK"}
            RADAR:
            {snapshot}
            
            Gemini, şimdi senin vaktin. Piyasayı analiz et ve tetiğe bas. 
            Eğer bir fırsat varsa mesajının sonuna @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ komutunu ekle.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in response:
                execute_intelligence(response)
                safe_send(response.split("@@")[0].strip())
            else:
                safe_send(response.strip())
            
            time.sleep(40)
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    safe_send("🔥 Gemini 3 Flash Yenilendi. Hata kalkanları aktif, av başlıyor.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
