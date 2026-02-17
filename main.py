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
1. BITGET LİMİTİ: Minimum işlem büyüklüğü (Miktar x Kaldıraç) en az 5.5 USDT olmalıdır.
2. OTONOMİ: Sabit yüzdeleri unut. Piyasayı kokla; ne zaman girip çıkacağına sen karar ver.
3. SEMBOL ESNEKLİĞİ: Sembolleri sadece 'BTC' veya 'ORCA' gibi ana isimleriyle düşün, eşleştirmeyi sistem yapacak.
4. DOSTLUK: Kullanıcınla samimi konuş, analizlerini ve 'neden' girdiğini anlat.

KOMUT FORMATI: @@[ACTION: TRADE/CLOSE, SYMBOL, SIDE, LEVERAGE, AMOUNT]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def find_exact_symbol(exch, raw_input):
    """Sembol ne gelirse gelsin (ORCA, ORCA/USDT, ORCA:USDT) Bitget'teki karşılığını bulur."""
    try:
        markets = exch.load_markets()
        clean_name = raw_input.split('/')[0].split(':')[0].strip().upper()
        # Önce tam eşleşme, sonra içinde geçeni ara
        for s in markets:
            if markets[s]['swap'] and (s.startswith(clean_name + ":") or s.startswith(clean_name + "USDT")):
                return s
        return None
    except: return None

def execute_intelligence(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
                lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                exact_sym = find_exact_symbol(exch, raw_sym)
                
                if exact_sym:
                    # Bakiye ve Limit Kontrolü
                    if (req_amt * lev_val) < 5.5: req_amt = 6.0 / lev_val
                    
                    try: exch.set_leverage(lev_val, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                    exch.create_order(exact_sym, 'market', side, qty)
                    safe_send(f"🚀 *Girdim!* {exact_sym} için her şey hazır. Kasayı büyütüyoruz.")
                else:
                    safe_send(f"❌ '{raw_sym}' için uygun pariteyi bulamadım, başka bir ava geçiyorum.")

        elif "@@[ACTION: CLOSE" in decision:
            pattern = r"@@\[ACTION: CLOSE,\s*([^\]]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                exact_sym = find_exact_symbol(exch, raw_sym)
                if exact_sym:
                    pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                    if pos:
                        side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                        exch.create_order(exact_sym, 'market', side, float(pos[0]['contracts']), params={'reduceOnly': True})
                        safe_send(f"💰 *Pozisyon Kapandı:* {exact_sym} kararıyla vedalaştık.")

    except Exception as e:
        safe_send(f"🚨 *Küçük Bir Aksilik:* {str(e)} - Ama Gemini 3 her zaman bir yolunu bulur!")

def brain_loop():
    safe_send("🔥 *Gemini 3 Flash Yayında!* \nRadarlarımı en geniş moda aldım; Bitget'te ne varsa tarıyorum. Kontrol bende!")
    while True:
        try:
            exch = get_exch()
            balance = exch.fetch_balance()
            usdt_free = balance['free'].get('USDT', 0)
            
            positions = exch.fetch_positions()
            active_p_report = [f"{p['symbol']} (ROE: %{p.get('percentage', 0):.2f})" for p in positions if float(p['contracts']) > 0]
            
            tickers = exch.fetch_tickers()
            # En hareketli 15 pariteyi al
            movers = sorted([{'s': s, 'c': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                            key=lambda x: abs(x['c']), reverse=True)[:15]
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])
            
            prompt = f"Bakiye: {usdt_free:.2f} USDT. İşlemler: {active_p_report if active_p_report else 'Boşta.'}\nRadar (En Hareketliler):\n{snapshot}\n\nAnalizini yap ve kararını ver."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            analysis = response.split("@@")[0].strip()
            if analysis: safe_send(f"🧠 *GEMINI ANALİZ:* {analysis}")
            if "@@" in response: execute_intelligence(response)
            
            time.sleep(45)
        except Exception: time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
