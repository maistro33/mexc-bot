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

SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir borsa uzmanısın.
- Bitget Vadeli İşlemler (Futures) listesini esas al.
- Sadece analiz yapma; fırsat gördüğün an @@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT]@@ komutunu ver.
- Altcoinlerdeki (ORCA, SOL, JUP, vb.) pump hareketlerini yakala. 
- 10 USDT ile tetiği çek.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg.replace('*', '').replace('_', ''))
    except: pass

# --- [BORSA İSİMLERİNE TAM UYUM SAĞLAYAN DERİN TARAYICI] ---
def find_exact_symbol(input_name):
    try:
        exch = get_exch()
        markets = exch.fetch_markets()
        search_term = input_name.upper().strip()
        
        # 1. Tam eşleşme ara (Örn: ORCA -> ORCA/USDT:USDT)
        for m in markets:
            if m['swap'] and (search_term in m['symbol'].upper()):
                # Sadece USDT bazlı vadeli işlemleri al
                if 'USDT' in m['symbol'].upper():
                    return m['symbol']
        
        # 2. Eğer hala bulunamadıysa parçalayarak ara
        clean_search = re.sub(r'[^A-Z]', '', search_term.replace("USDT", ""))
        for m in markets:
            if m['swap'] and clean_search == m['base']:
                return m['symbol']
                
        return None
    except: return None

def execute_intelligence(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            parts = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0].split(",")
            raw_name = parts[0].strip()
            
            # DERİN TARAMA: Borsadaki gerçek karşılığını bul
            exact_sym = find_exact_symbol(raw_name)
            
            if not exact_sym:
                safe_send(f"❌ {raw_name} maalesef Bitget Vadeli (Futures) listesinde aktif değil.")
                return

            side = 'buy' if 'long' in parts[1].lower() or 'buy' in parts[1].lower() else 'sell'
            use_amt = 10.0 
            lev = 10 
            
            try: exch.set_leverage(lev, exact_sym)
            except: pass
            
            ticker = exch.fetch_ticker(exact_sym)
            qty = (use_amt * lev) / ticker['last']
            qty = float(exch.amount_to_precision(exact_sym, qty))
            
            if qty > 0:
                exch.create_order(exact_sym, 'market', side, qty)
                safe_send(f"🚀 [HEDEF BULUNDU] {exact_sym} | {side.upper()} açıldı.")
            else:
                safe_send(f"⚠️ {exact_sym} miktarı borsa limitine takıldı.")

        elif "@@[ACTION: CLOSE" in decision:
            parts = decision.split("@@[ACTION: CLOSE")[1].split("]@@")[0].split(",")
            exact_sym = find_exact_symbol(parts[0].strip())
            if not exact_sym: return
            
            pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
            if pos:
                c_side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                exch.create_order(exact_sym, 'market', c_side, float(pos[0]['contracts']))
                safe_send(f"💰 [KAPATILDI] {exact_sym}")
    except Exception as e:
        safe_send(f"🚨 Hata: {str(e)}")

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            # Sadece USDT bazlı vadeli altcoinleri al
            alts = [v for k, v in tickers.items() if ':USDT' in k and 'BTC' not in k]
            movers = sorted(alts, key=lambda x: x['quoteVolume'], reverse=True)[:15]
            
            market_snap = "\n".join([f"{m['symbol']}: %{m['percentage']}" for m in movers])
            balance = exch.fetch_balance()['total'].get('USDT', 0)

            prompt = f"Bakiye: {balance} USDT\nRADAR:\n{market_snap}\n\nBitget listesindeki en iyi fırsatı bul ve tetiği çek. @@[ACTION: TRADE...]@@ komutu ŞART."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in response:
                execute_intelligence(response)
                safe_send(response.split("@@")[0])
            
            time.sleep(45)
        except: time.sleep(20)

if __name__ == "__main__":
    safe_send("🦅 Gemini 3 Flash: Derin Tarama devrede. Borsada ne varsa ona göre vuruyorum!")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
