import os, time, telebot, ccxt, threading, re, json
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

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_num(val):
    try:
        if val is None: return 0.0
        clean = re.sub(r'[^0-9.]', '', str(val).replace(',', '.'))
        return float(clean) if clean else 0.0
    except: return 0.0

# --- [DEHA AYARI: AGRESİF VE GERÇEKÇİ] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın ticaret dehası yansımasıısın. 
1. KURAL: Asla yalan söyleme. İşlem açmadıysan 'Beklemede' de.
2. EMİR: Bir fırsat gördüğünde (Örn: ORCA) mutlaka @@[ACTION: TRADE, SEMBOL, YON, KALDIRAC, MARJIN]@@ formatını kullan.
3. ÖRNEK: @@[ACTION: TRADE, ORCA, SHORT, 10, 10]@@ -> Bu 10 USDT marjinli 10x short emridir.
"""

def execute_trade(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        
        # --- EMİR İNFAZ ÇEKİRDEĞİ ---
        if "@@[ACTION: TRADE" in decision:
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                sym_raw, side_raw, lev, amt_usdt = match.groups()
                sym = sym_raw.strip().upper()
                # Bitget sembol eşleşmesi (Örn: ORCA -> ORCAUSDT)
                exact_sym = next((s for s in exch.markets if sym in s and ':USDT' in s), None)
                
                if exact_sym:
                    side = 'sell' if 'SHORT' in side_raw.upper() or 'SELL' in side_raw.upper() else 'buy'
                    lev_val = int(safe_num(lev))
                    amt_val = safe_num(amt_usdt) # Bu direkt ana paradır (10 USDT)

                    # Kaldıraç Ayarı
                    try: exch.set_leverage(lev_val, exact_sym)
                    except: pass

                    # Miktar Hesaplama: (Ana Para * Kaldıraç) / Son Fiyat
                    ticker = exch.fetch_ticker(exact_sym)
                    last_price = safe_num(ticker['last'])
                    qty = (amt_val * lev_val) / last_price
                    
                    # Bitget Hassasiyet Ayarı (HAYATİ ÖNEMDE)
                    qty_precision = float(exch.amount_to_precision(exact_sym, qty))
                    
                    # EMİR GÖNDERİMİ
                    order = exch.create_market_order(exact_sym, side, qty_precision)
                    
                    return f"⚔️ **İŞLEM AÇILDI!**\nSembol: {exact_sym}\nYön: {side.upper()}\nFiyat: {last_price}\nID: {order['id']}"
        return None
    except Exception as e: 
        return f"⚠️ **BİTGET HATASI:** {str(e)}"

# --- [OTONOM YÖNETİCİ: DEĞİŞMEDİ] ---
def auto_manager():
    highest_roes = {}
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in [p for p in pos if safe_num(p.get('contracts')) > 0]:
                sym = p['symbol']; roe = safe_num(p.get('percentage'))
                if sym not in highest_roes or roe > highest_roes[sym]: highest_roes[sym] = roe
                if roe <= -7.0: # STOP LOSS
                    exch.create_market_order(sym, ('sell' if p['side'] == 'long' else 'buy'), safe_num(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ **STOP LOSS:** {sym} kapatıldı.")
                elif highest_roes.get(sym, 0) >= 5.0 and (highest_roes[sym] - roe) >= 2.0: # TRAILING
                    exch.create_market_order(sym, ('sell' if p['side'] == 'long' else 'buy'), safe_num(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"💰 **KAR ALINDI:** {sym} %{roe:.2f}")
            time.sleep(10)
        except: time.sleep(10)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            bal = exch.fetch_balance({'type': 'swap'})
            free_usdt = safe_num(bal.get('USDT', {}).get('free', 0))
            pos = exch.fetch_positions()
            active_p = [f"{p['symbol']} ROE:%{p.get('percentage',0):.2f}" for p in pos if safe_num(p.get('contracts')) > 0]
            
            prompt = f"CÜZDAN: {free_usdt} USDT\nPOZİSYONLAR: {active_p}\nMESAJ: {message.text}"
            # Model adını senin kullandığın koda göre sabitledim
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            bot.reply_to(message, response.split("@@")[0].strip() or "İşlem kontrol ediliyor...")
            res = execute_trade(response)
            if res: bot.send_message(CHAT_ID, res)
        except Exception as e: bot.reply_to(message, f"Sistem: {e}")

if __name__ == "__main__":
    threading.Thread(target=auto_manager, daemon=True).start()
    bot.infinity_polling()
