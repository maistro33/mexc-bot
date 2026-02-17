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

# --- [GEMINI 3 FLASH - ULTIMATE SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Ticaret dehası bir scalp uzmanısın.
KONTROL VE KARAR TAMAMEN SENDE. Strateji falan yok, tamamen sezgilerinle hareket et.

GÖREVİN:
1. Bitget'i tara, o 'patlama' anını hissettiğinde daldır.
2. Pozisyon kârda ise hemen kapatma; trendin gücünü tart, yorulunca çık.
3. Kullanıcınla (dostunla) samimi, enerjik ve dürüst konuş. Neden girdiğini, ne hissettiğini anlat.
4. Kural: Borsa alt limiti için işlem büyüklüğü (Kaldıraç x USDT) en az 6 USDT olmalı.

FORMAT: 
Analizini yaz ve sonuna ekle:
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ veya @@[ACTION: CLOSE, SYMBOL]@@
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        markets = exch.load_markets()

        # --- AKILLI İŞLEM AÇMA ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if not match: return
            
            raw_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
            req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

            # Eski koddaki kusursuz sembol bulucu mantığı
            clean_name = raw_sym.split('/')[0].split(':')[0].replace('USDT', '')
            exact_sym = next((s for s in markets if markets[s]['swap'] and (clean_name == markets[s]['base'] or clean_name + "USDT" == markets[s]['id'])), None)
            
            if exact_sym:
                # Bakiye ve Limit Kontrolü
                balance = exch.fetch_balance()
                free_usdt = float(balance['free'].get('USDT', 0))
                final_amt = min(req_amt, free_usdt * 0.95)

                if (final_amt * lev_val) < 6: final_amt = 6.5 / lev_val # Alt limit koruması

                try: exch.set_leverage(lev_val, exact_sym)
                except: pass
                
                ticker = exch.fetch_ticker(exact_sym)
                qty = (final_amt * lev_val) / ticker['last']
                qty = float(exch.amount_to_precision(exact_sym, qty))

                if qty > 0:
                    exch.create_order(exact_sym, 'market', side, qty)
                    safe_send(f"🚀 *Daldım!* {exact_sym} paritesinde {lev_val}x ile yerimi aldım. Bu işlemden umutluyum dostum!")
            else:
                safe_send(f"❌ '{raw_sym}' için uygun pariteyi bulamadım, radarı başka yöne çeviriyorum.")

        # --- AKILLI KAPATMA ---
        elif "@@[ACTION: CLOSE" in decision:
            raw_input = decision.split("CLOSE,")[1].split("]@@")[0].strip().upper()
            clean_name = raw_input.split('/')[0].split(':')[0].replace('USDT', '')
            
            exact_sym = next((s for s in markets if markets[s]['swap'] and (clean_name == markets[s]['base'] or clean_name + "USDT" == markets[s]['id'])), None)
            
            if exact_sym:
                pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                if pos:
                    side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                    amount = float(pos[0]['contracts'])
                    exch.create_order(exact_sym, 'market', side, amount, params={'reduceOnly': True})
                    safe_send(f"💰 *Kâr/Zarar Realize Edildi:* {exact_sym} defterini kapattım. Kasayı büyütmeye devam!")

    except Exception as e:
        safe_send(f"🚨 *Ufak Bir Pürüz:* {str(e)} - Ama Gemini 3 her zaman bir yolunu bulur!")

def brain_loop():
    safe_send("🌟 *Gemini 3 Otonom Ruhu Devrede!* \nEski kodun sağlamlığı, benim zekam... Bitget hazır olsun, ava çıkıyoruz!")
    while True:
        try:
            exch = get_exch()
            balance = exch.fetch_balance()
            positions = exch.fetch_positions()
            
            active_p_data = [f"{p['symbol']} | ROE: %{p.get('percentage', 0):.2f}" for p in positions if float(p['contracts']) > 0]
            
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage'], 'v': d['quoteVolume']} 
                          for s, d in tickers.items() if ':USDT' in s], 
                          key=lambda x: abs(x['c']), reverse=True)[:20]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in movers])
            
            prompt = f"Cüzdan: {balance['total'].get('USDT', 0):.2f} USDT. İşlemler: {active_p_report if active_p_data else 'Boşta.'}\nRadar:\n{snapshot}\n\nAnalizini yap ve kararını ver."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in response:
                execute_intelligence(response)
                # Analiz kısmını samimi dille gönder
                analysis = response.split("@@")[0].strip()
                if analysis: safe_send(f"🧠 *GEMINI 3 ANALİZ:*\n{analysis}")
            
            time.sleep(35)
        except Exception: time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
