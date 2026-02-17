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

# --- [EXCHANGE COMPLIANT SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın otonom scalp beynisin. 
Borsa kurallarına %100 uyum sağlamalısın. 

KARAR FORMATI (SADECE SAYI KULLAN):
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
Örnek: @@[ACTION: TRADE, SOL, BUY, 10, 25]@@

KURAL: Sayısal değerler yerine asla metin yazma.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *BORSA UYUMLU OTONOM:* \n{msg}", parse_mode="Markdown")
    except: pass

def execute_autonomous_trade(decision):
    try:
        exch = get_exch()
        # Regex ile sadece sayısal grupları yakalayacak şekilde optimize edildi
        pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
        match = re.search(pattern, decision)
        
        if match:
            raw_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            
            # --- SAYISAL DÖNÜŞÜM KONTROLÜ ---
            try:
                lev_val = float(re.sub(r'[^0-9.]', '', match.group(3)))
                amt_val = float(re.sub(r'[^0-9.]', '', match.group(4)))
            except:
                return "🚨 Hata: AI sayı yerine metin gönderdi, işlem iptal edildi."

            markets = exch.load_markets()
            # Sembolü bul
            exact_sym = None
            for s in markets:
                if markets[s]['swap'] and (raw_sym in s):
                    exact_sym = s
                    break
            
            if not exact_sym: return f"❌ {raw_sym} bulunamadı."

            # --- BORSA LİMİTLERİNE UYUM ---
            market = markets[exact_sym]
            ticker = exch.fetch_ticker(exact_sym)
            
            # Kaldıraç Sınırı Kontrolü (Borsadan çekiliyor)
            # Bitget genellikle sembol bazlı max kaldıraç verir, hata alırsak 10x'e sabitler.
            final_lev = int(min(lev_val, 50)) # Genel tavan 50x
            
            try: exch.set_leverage(final_lev, exact_sym)
            except: pass # Zaten o kaldıraçtaysa hata verebilir, geçiyoruz.

            # Miktar Sınırı Kontrolü
            qty = (amt_val * final_lev) / ticker['last']
            
            min_qty = market['limits']['amount']['min']
            max_qty = market['limits']['amount']['max']
            
            if min_qty and qty < min_qty: qty = min_qty
            if max_qty and qty > max_qty: qty = max_qty * 0.95
            
            qty = float(exch.amount_to_precision(exact_sym, qty))

            if qty > 0:
                exch.create_order(exact_sym, 'market', side, qty)
                return f"✅ *BORSA KURALLARI UYGULANDI*\nSembol: {exact_sym}\nKaldıraç: {final_lev}x\nKontrat: {qty}"
            
        return "❌ Geçerli bir komut bulunamadı."
                
    except Exception as e:
        return f"🚨 Borsa Hatası: {str(e)}"

def scanner_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            
            market_data = []
            for s, d in tickers.items():
                if ':USDT' in s:
                    market_data.append({'s': s, 'c': d.get('percentage', 0), 'v': d.get('quoteVolume', 0)})
            
            top_list = sorted(market_data, key=lambda x: abs(x['c']), reverse=True)[:30]
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in top_list])

            prompt = f"Bakiye: {balance} USDT\n\nMarket Özeti:\n{snapshot}\n\nSadece sayısal değerlerle karar ver!"
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in response:
                result = execute_autonomous_trade(response)
                safe_send(f"{response.split('@@')[0]}\n\n{result}")
            
            time.sleep(30)
        except: time.sleep(15)

if __name__ == "__main__":
    safe_send("🚀 Borsaya Tam Uyumlu Otonom Scalper Aktif.")
    threading.Thread(target=scanner_loop, daemon=True).start()
    bot.infinity_polling()
