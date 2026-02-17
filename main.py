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
Sen Gemini 3 Flash'sın. Bitget borsasında kendi sezgileriyle takılan bir ticaret dehasısın.
KONTROL TAMAMEN SENDE. Strateji, giriş ve çıkış kararlarını piyasayı koklayarak kendin veriyorsun.

ÖNEMLİ:
1. BITGET MİNYATÜR KURALI: Toplam işlem büyüklüğü (Miktar x Kaldıraç) en az 6 USDT olsun ki hata almayalım.
2. OTONOMİ: Sabit yüzdeleri unut. Ne zaman girip çıkacağına sen karar ver.
3. DOSTLUK: Kullanıcınla samimi konuş. "Şunu hissettim, şuradan daldım, şu yüzden kaçtım" de.
4. FORMAT: Kararını mutlaka şu formatta bitir: @@[ACTION: TRADE/CLOSE, SYMBOL, SIDE, LEVERAGE, AMOUNT]@@
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
    try:
        markets = exch.load_markets()
        clean_name = re.sub(r'[^A-Z]', '', raw_input.upper().replace('USDT', ''))
        for s in markets:
            if markets[s]['swap'] and (s.startswith(clean_name + ":") or s.startswith(clean_name + "USDT")):
                return s
        return None
    except: return None

def extract_number(text):
    """Metin içinden sayıları güvenli bir şekilde çeker, hata payını sıfırlar."""
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    return float(nums[0]) if nums else 0.0

def execute_intelligence(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip()
                side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
                
                # Hata aldığın o kritik sayı ayıklama kısımları:
                lev_val = int(extract_number(match.group(3)))
                req_amt = extract_number(match.group(4))

                exact_sym = find_exact_symbol(exch, raw_sym)
                if exact_sym and lev_val > 0 and req_amt > 0:
                    # Borsa Limit Koruması (Minimum 6 USDT büyüklük)
                    if (req_amt * lev_val) < 6: req_amt = 6.5 / lev_val
                    
                    try: exch.set_leverage(lev_val, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                    exch.create_order(exact_sym, 'market', side, qty)
                    safe_send(f"🚀 *Sinyali Aldım!* {exact_sym} paritesine daldım. Kontrol tamamen bende, kârı kovalıyorum!")
                else:
                    safe_send(f"❌ Sembol veya miktar hatası, '{raw_sym}' için uygun işlem yapılamadı.")

        elif "@@[ACTION: CLOSE" in decision:
            pattern = r"@@\[ACTION: CLOSE,\s*([^\]]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip()
                exact_sym = find_exact_symbol(exch, raw_sym)
                if exact_sym:
                    pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                    if pos:
                        side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                        exch.create_order(exact_sym, 'market', side, float(pos[0]['contracts']), params={'reduceOnly': True})
                        safe_send(f"💰 *Kâr Realize Edildi!* {exact_sym} defterini şimdilik kapattım. Başka ava gidiyoruz!")

    except Exception as e:
        safe_send(f"🚨 *Küçük Bir Ayar Lazım:* {str(e)} - Ama Gemini 3 her zaman bir yolunu bulur!")

def brain_loop():
    safe_send("🌟 *Gemini 3 Canlandı!* Artık hatalara karşı daha dirençliyim. Bitget'i taramaya ve seninle konuşmaya başlıyorum.")
    while True:
        try:
            exch = get_exch()
            balance = exch.fetch_balance()
            usdt_free = balance['free'].get('USDT', 0)
            
            positions = exch.fetch_positions()
            active_p_report = [f"{p['symbol']} (ROE: %{p.get('percentage', 0):.2f})" for p in positions if float(p['contracts']) > 0]
            
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                            key=lambda x: abs(x['c']), reverse=True)[:15]
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])
            
            prompt = f"Bakiye: {usdt_free:.2f} USDT. İşlemler: {active_p_report if active_p_report else 'Boşta.'}\nRadar:\n{snapshot}\n\nSezgilerini kullan ve analizini yap."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            analysis = response.split("@@")[0].strip()
            if analysis: safe_send(f"🧠 *ANALİZ:* {analysis}")
            if "@@" in response: execute_intelligence(response)
            
            time.sleep(45)
        except Exception: time.sleep(25)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
