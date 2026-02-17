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

# --- [DYNAMIC & ROBUST SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın otonom scalp beynisin. 
KOMUTLARDA ASLA BOŞLUK BIRAKMA. SADECE SAYI KULLAN.
FORMAT: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *BORSA UYUMLU OTONOM:* \n{msg}", parse_mode="Markdown")
    except: pass

def clean_to_float(text, default=0.0):
    """Metni sayıya çevirir, hata veya boşluk durumunda varsayılan değeri döner"""
    try:
        cleaned = re.sub(r'[^0-9.]', '', text)
        return float(cleaned) if cleaned else default
    except:
        return default

def execute_intelligence(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if not match: return
            
            raw_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            
            # --- HATA ÖNLEYİCİ SAYI DÖNÜŞÜMÜ ---
            lev_val = int(clean_to_float(match.group(3), default=2.0)) # Boşsa 2x
            req_amt = clean_to_float(match.group(4), default=10.0)    # Boşsa 10 USDT

            markets = exch.load_markets()
            exact_sym = next((s for s in markets if markets[s]['swap'] and raw_sym in s), None)
            if not exact_sym: return

            balance = exch.fetch_balance()
            free_usdt = float(balance['free'].get('USDT', 0))
            final_amt = min(req_amt, free_usdt * 0.9)

            if final_amt < 5: return

            try: exch.set_leverage(lev_val, exact_sym)
            except: pass
            
            ticker = exch.fetch_ticker(exact_sym)
            qty = (final_amt * lev_val) / ticker['last']
            
            market = markets[exact_sym]
            max_qty = market['limits']['amount']['max']
            if max_qty and qty > max_qty: qty = max_qty * 0.9
            
            qty = float(exch.amount_to_precision(exact_sym, qty))
            if qty > 0:
                exch.create_order(exact_sym, 'market', side, qty)
                safe_send(f"✅ *İŞLEM AÇILDI:* {exact_sym}\nKaldıraç: {lev_val}x\nMiktar: {final_amt:.2f} USDT")

        elif "@@[ACTION: CLOSE" in decision:
            raw_input = decision.split("CLOSE,")[1].split("]@@")[0].strip().upper()
            clean_name = raw_input.split('/')[0].split(':')[0]
            
            markets = exch.load_markets()
            exact_sym = next((s for s in markets if (m:=markets[s])['swap'] and (clean_name == m['base'] or clean_name + "USDT" == m['id'])), None)
            
            if exact_sym:
                pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                if pos:
                    side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                    exch.create_order(exact_sym, 'market', side, float(pos[0]['contracts']), params={'reduceOnly': True})
                    safe_send(f"💰 *KAPATILDI:* {exact_sym}")

    except Exception as e:
        safe_send(f"🚨 Sistem Uyarısı (Hata Giderildi): {str(e)}")

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            active_p = [f"{p['symbol']} (%{p.get('percentage', 0):.2f})" for p in exch.fetch_positions() if float(p['contracts']) > 0]
            
            movers = sorted([{'s': s, 'c': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                            key=lambda x: abs(x['c']), reverse=True)[:25]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']}" for x in movers])
            
            prompt = f"Bakiye: {balance['free'].get('USDT', 0)} USDT\nPozisyonlar: {active_p}\nRadar:\n{snapshot}\n\nKararını ver."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            if "@@" in response:
                execute_intelligence(response)
                safe_send(response.split("@@")[0])
            
            time.sleep(30)
        except: time.sleep(15)

if __name__ == "__main__":
    safe_send("🔥 *Gemini 3 Otonom v5 Başladı!* \nBoş değer ve string dönüştürme hataları giderildi.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
