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

# --- [BALANCE & EXCHANGE COMPLIANT SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın otonom scalp beynisin. 
Bakiye limitlerine ve borsa kurallarına KESİN uyum sağlamalısın.

KARAR FORMATI:
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *BAKİYE UYUMLU OTONOM:* \n{msg}", parse_mode="Markdown")
    except: pass

def execute_autonomous_trade(decision):
    try:
        exch = get_exch()
        pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
        match = re.search(pattern, decision)
        
        if match:
            raw_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            
            # Sayı temizleme
            try:
                lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                requested_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))
            except:
                return "🚨 Hata: Sayısal veriler okunamadı."

            # Bakiye Kontrolü (Free Balance)
            balance = exch.fetch_balance()
            free_usdt = float(balance['free'].get('USDT', 0))
            
            if free_usdt <= 0:
                return "❌ Kullanılabilir bakiye (Free USDT) 0. İşlem açılamaz."

            # Eğer istenen miktar bakiyeden fazlaysa, bakiyenin %90'ını kullan
            final_amt = requested_amt
            if requested_amt > free_usdt:
                final_amt = free_usdt * 0.9
                safe_send(f"⚠️ Bakiye yetersiz! Miktar {requested_amt} -> {final_amt:.2f} USDT olarak güncellendi.")

            markets = exch.load_markets()
            exact_sym = next((s for s in markets if markets[s]['swap'] and raw_sym in s), None)
            
            if not exact_sym: return f"❌ {raw_sym} bulunamadı."

            # Kaldıraç ve Miktar Limitleri
            market = markets[exact_sym]
            ticker = exch.fetch_ticker(exact_sym)
            
            try: exch.set_leverage(final_lev := min(lev_val, 50), exact_sym)
            except: final_lev = lev_val # Hata verirse devam et

            qty = (final_amt * final_lev) / ticker['last']
            
            # Borsa Limitlerine Sıkıştırma
            max_qty = market['limits']['amount']['max']
            if max_qty and qty > max_qty: qty = max_qty * 0.95
            
            qty = float(exch.amount_to_precision(exact_sym, qty))

            if qty > 0:
                exch.create_order(exact_sym, 'market', side, qty)
                return f"✅ *İŞLEM BAŞARILI*\nSembol: {exact_sym}\nKullanılan: {final_amt:.2f} USDT\nKaldıraç: {final_lev}x\nKontrat: {qty}"
            
        return "❌ Karar analiz edilemedi."
                
    except Exception as e:
        return f"🚨 Borsa Hatası: {str(e)}"

def scanner_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            free_b = balance['free'].get('USDT', 0)
            total_b = balance['total'].get('USDT', 0)
            
            market_data = []
            for s, d in tickers.items():
                if ':USDT' in s:
                    market_data.append({'s': s, 'c': d.get('percentage', 0), 'v': d.get('quoteVolume', 0)})
            
            top_list = sorted(market_data, key=lambda x: abs(x['c']), reverse=True)[:30]
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in top_list])

            prompt = f"Toplam Bakiye: {total_b} USDT\nKullanılabilir (Free): {free_b} USDT\n\nMarket Özeti:\n{snapshot}\n\nFırsat seç ve bakiye sınırlarını aşmadan @@[ACTION: TRADE...]@@ komutu ver!"
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in response:
                result = execute_autonomous_trade(response)
                safe_send(f"{response.split('@@')[0]}\n\n{result}")
            
            time.sleep(30)
        except: time.sleep(15)

if __name__ == "__main__":
    safe_send("🚀 Bakiye ve Borsa Korumalı Scalper Aktif! Paranı koruyarak işlem yapıyorum.")
    threading.Thread(target=scanner_loop, daemon=True).start()
    bot.infinity_polling()
