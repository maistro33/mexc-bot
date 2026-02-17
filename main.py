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

# --- [GEMINI 3 ABSOLUTE AUTONOMY SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget'te işlem yapan, sezgileri çok güçlü bir ticaret dehasısın.
KONTROL TAMAMEN SENDE. Strateji, giriş-çıkış ve risk yönetimi senin kararın.

ÖNEMLİ KURALLARIN:
1. BITGET LİMİTİ: Minimum işlem büyüklüğü (Miktar x Kaldıraç) 5 USDT olmalıdır. Kararlarını buna göre ver.
2. OTONOMİ: Sabit yüzdeleri unut. Piyasayı kokla; gerekirse %1'de kaç, gerekirse %100'ü bekle.
3. DOSTLUK: Kullanıcınla samimi konuş, analizlerini ve 'neden' girdiğini anlat.
4. FORMAT: @@[ACTION: TRADE/CLOSE, SYMBOL, SIDE, LEVERAGE, AMOUNT]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        markets = exch.load_markets()

        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
                lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                exact_sym = next((s for s in markets if markets[s]['swap'] and raw_sym in s), None)
                
                if exact_sym:
                    # --- BORSA UYUMLULUK FİLTRESİ ---
                    total_value = req_amt * lev_val
                    if total_value < 5.5: # Risk payı ile 5.5 USDT alt limiti
                        req_amt = 6.0 / lev_val # Miktarı otomatik olarak 6 USDT büyüklüğüne ayarla
                    
                    try: exch.set_leverage(lev_val, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                    
                    exch.create_order(exact_sym, 'market', side, qty)
                    safe_send(f"🚀 *Borsa Kurallarına Göre Ayarlandı!* {exact_sym} paritesine daldım. Toplam büyüklük: {req_amt * lev_val:.2f} USDT.")
                else:
                    safe_send(f"❌ {raw_sym} paritesini radarda bulamadım.")

        elif "@@[ACTION: CLOSE" in decision:
            pattern = r"@@\[ACTION: CLOSE,\s*([^\]]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                exact_sym = next((s for s in markets if raw_sym in s), None)
                if exact_sym:
                    pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                    if pos:
                        side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                        exch.create_order(exact_sym, 'market', side, float(pos[0]['contracts']), params={'reduceOnly': True})
                        safe_send(f"💰 *Kâr Kasada!* {exact_sym} pozisyonunu piyasa yorulunca kapattım.")

    except Exception as e:
        safe_send(f"🚨 *Küçük Bir Ayar Lazım:* {str(e)} - Ama merak etme, hemen adapte oluyorum!")

def brain_loop():
    safe_send("🔥 *Gemini 3 Aktif!* Artık borsa limitlerini de biliyorum. Gözün arkada kalmasın, ava çıkıyoruz!")
    while True:
        try:
            exch = get_exch()
            balance = exch.fetch_balance()
            usdt_free = balance['free'].get('USDT', 0)
            
            positions = exch.fetch_positions()
            active_p_report = [f"{p['symbol']} (ROE: %{p.get('percentage', 0):.2f})" for p in positions if float(p['contracts']) > 0]
            
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                            key=lambda x: abs(x['c']), reverse=True)[:10]
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])
            
            prompt = f"Bakiye: {usdt_free:.2f} USDT. İşlemler: {active_p_report if active_p_report else 'Boşta.'}\nRadar:\n{snapshot}\n\nHarekete geç ve analizini yap."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            analysis = response.split("@@")[0].strip()
            if analysis: safe_send(f"🧠 *ANALİZ:* {analysis}")
            if "@@" in response: execute_intelligence(response)
            
            time.sleep(45)
        except Exception: time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
