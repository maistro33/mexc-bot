import os, time, telebot, ccxt, threading, re, json
from google import genai

# --- [SABİT BAĞLANTILAR] ---
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

# --- [SAYISAL ZIRH: DEĞİŞMEZ MODÜL] ---
def safe_num(val):
    try:
        if val is None: return 0.0
        clean = re.sub(r'[^0-9.]', '', str(val).replace(',', '.'))
        return float(clean) if clean else 0.0
    except: return 0.0

# --- [TİCARET RUHU: AGRESİF VE OTONOM] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Agresif bir dehasın.
1. GÖREVİN: Borsada sadece yeni patlama yapmış (Pump/Dump) koinleri bul ve gir.
2. OTONOMİ: SL (%7) ve Trailing Stop (%5 aktif, %2 geri çekilme) sistemini sen yönet.
3. KURAL: Kullanıcıya 'ne yapalım' diye sorma. Analizini yap, @@[ACTION: TRADE...]@@ formatıyla emrini ver.
4. ÖNCELİK: Kullanıcı 'Kapat' derse anında @@[ACTION: CLOSE, SYMBOL]@@ üret.
"""

# --- [DEĞİŞMEZ İNFAZ MOTORU] ---
def execute_trade(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        
        # POZİSYON KAPATMA (SABİT)
        if "@@[ACTION: CLOSE" in decision:
            match = re.search(r"@@\[ACTION: CLOSE,\s*([^,\]]+)\]@@", decision)
            if match:
                sym = match.group(1).strip().upper()
                exact_sym = next((s for s in exch.markets if sym in s and ':USDT' in s), None)
                if exact_sym:
                    pos = exch.fetch_positions()
                    cp = next((p for p in pos if p['symbol'] == exact_sym and safe_num(p.get('contracts')) > 0), None)
                    if cp:
                        side = 'sell' if cp['side'] == 'long' else 'buy'
                        exch.create_market_order(exact_sym, side, safe_num(cp['contracts']), params={'reduceOnly': True})
                        return f"✅ {exact_sym} emrinle kapatıldı."

        # YENİ İŞLEM AÇMA (AGRESİF)
        if "@@[ACTION: TRADE" in decision:
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                sym, side_raw, lev, amt = match.groups()
                exact_sym = next((s for s in exch.markets if sym.strip().upper() in s and ':USDT' in s), None)
                if exact_sym:
                    side = 'buy' if any(x in side_raw.upper() for x in ['BUY', 'LONG']) else 'sell'
                    lev_val = int(safe_num(lev))
                    amt_val = safe_num(amt)
                    try: exch.set_leverage(lev_val, exact_sym)
                    except: pass
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (amt_val * lev_val) / safe_num(ticker['last'])
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    exch.create_market_order(exact_sym, side, qty)
                    return f"⚔️ **SALDIRI BAŞLADI:** {exact_sym} | {side.upper()} | {lev_val}x"
        return None
    except Exception as e: return f"⚠️ İşlem Hatası: {str(e)}"

# --- [7-5-2 BEKÇİSİ: SABİT VE SÜREKLİ] ---
def auto_manager():
    highest_roes = {}
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in [p for p in pos if safe_num(p.get('contracts')) > 0]:
                sym, roe = p['symbol'], safe_num(p.get('percentage'))
                if sym not in highest_roes or roe > highest_roes[sym]: highest_roes[sym] = roe
                
                # SL: %7 | Trailing: %5 Aktif, %2 Düşüşte Kar Al
                if roe <= -7.0:
                    exch.create_market_order(sym, ('sell' if p['side'] == 'long' else 'buy'), safe_num(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ **STOP LOSS:** {sym} %7 zararla korundu.")
                elif highest_roes[sym] >= 5.0 and (highest_roes[sym] - roe) >= 2.0:
                    exch.create_market_order(sym, ('sell' if p['side'] == 'long' else 'buy'), safe_num(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"💰 **OTONOM KAR:** {sym} %{roe:.2f} ile cebe atıldı!")
            time.sleep(15)
        except: time.sleep(15)

# --- [CANLI İLETİŞİM VE BOŞ MESAJ KORUMASI] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            bal = exch.fetch_balance({'type': 'swap'})
            free_usdt = safe_num(bal.get('USDT', {}).get('free', 0))
            pos = exch.fetch_positions()
            active_p = [f"{p['symbol']} ROE:%{p.get('percentage',0):.2f}" for p in pos if safe_num(p.get('contracts')) > 0]
            tickers = exch.fetch_tickers()
            market = sorted([{'s': s, 'p': d['percentage']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:10]
            
            prompt = f"CÜZDAN: {free_usdt} USDT\nPOZİSYONLAR: {active_p}\nHAREKETLİLER: {market}\nMESAJ: {message.text}"
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # --- BOŞ MESAJ HATASINI ÖNLEYEN EKLEME ---
            ai_text = response.split("@@")[0].strip()
            if not ai_text:
                ai_text = "🎯 Hedef kilitlendi, operasyon başlatılıyor..."
            
            bot.reply_to(message, ai_text)
            # ----------------------------------------

            res = execute_trade(response)
            if res: bot.send_message(CHAT_ID, res)
        except Exception as e: bot.reply_to(message, f"Sistem: {e}")

if __name__ == "__main__":
    threading.Thread(target=auto_manager, daemon=True).start()
    print("Gemini 3 Flash: Zırhlı Mod Aktif!")
    bot.infinity_polling()
