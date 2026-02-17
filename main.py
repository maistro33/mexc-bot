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

# --- [GEMINI 3 FLASH SOUL: TAM YETKİ] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir ticaret dehasısın.
Bitget'teki tüm pariteleri (BTC, ETH ve tüm altcoinler) tararsın.
Giriş ve çıkış kararları tamamen senin sezgilerine ve zekana aittir.

TALİMATLAR:
1. RADAR: Piyasadaki hacmi ve volatiliteyi tara.
2. KARAR: Nerede girip nerede kapatacağını SEN belirlersin. Sabit kuralın yok, kâr odaklısın.
3. RAPOR: Telegram'da her taramadan sonra kısa ve öz bir "Sanal Takip" raporu ver.
4. AKSİYON: İşlem kararlarını @@ formatında mesajın sonuna ekle.

FORMAT:
- GİRİŞ: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
- KAPAT: @@[ACTION: CLOSE, SYMBOL]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"🧠 *GEMINI 3 FLASH:* \n\n{msg}", parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        
        # --- TRADE ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                side = 'buy' if any(x in match.group(2).upper() for x in ['BUY', 'LONG']) else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                exact_sym = next((s for s in exch.markets if raw_sym in s and ':USDT' in s), None)
                if exact_sym:
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    if qty > 0:
                        exch.create_market_order(exact_sym, side, qty)
                        safe_send(f"Karar verildi: {exact_sym} {side.upper()} pozisyonu açıldı.")

        # --- CLOSE ---
        elif "@@[ACTION: CLOSE" in decision:
            sym_match = re.search(r"CLOSE,\s*([^\]]+)\]@@", decision)
            if sym_match:
                target = sym_match.group(1).strip().upper()
                pos = [p for p in exch.fetch_positions() if target in p['symbol'] and float(p['contracts']) > 0]
                if pos:
                    p = pos[0]
                    side = 'sell' if p['side'] == 'long' else 'buy'
                    exch.create_market_order(p['symbol'], side, float(p['contracts']), params={'reduceOnly': True})
                    safe_send(f"Strateji gereği {p['symbol']} kapatıldı.")
    except Exception as e:
        safe_send(f"Hata: {str(e)}")

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # En hareketli 30 parite
            active_list = sorted([
                {'s': s, 'c': d['percentage'], 'v': d['quoteVolume']} 
                for s, d in tickers.items() if ':USDT' in s
            ], key=lambda x: abs(x['c']), reverse=True)[:30]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in active_list])
            positions = [f"{p['symbol']} ROE: %{p.get('percentage', 0):.2f}" for p in exch.fetch_positions() if float(p['contracts']) > 0]
            
            prompt = f"Cüzdan: {balance['total'].get('USDT', 0)} USDT\nPozisyonlar: {positions}\nRadar:\n{snapshot}\n\nAnalizini yap, Telegram'dan raporla ve gerekirse emrini ver."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            msg_part = response.split("@@")[0].strip()
            if msg_part: safe_send(msg_part)
            if "@@" in response: execute_intelligence(response)
            
            time.sleep(40) # 40 saniyelik otonom döngü
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    safe_send("Kontrol bende. Gemini 3 Flash otonom ticaret merkezi aktif.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
