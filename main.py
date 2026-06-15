#!/usr/bin/env python3
"""
SADIK DYNAMIC SCANNER BOT v5
Baz: v2 + TP1/TP2/TP3 + Breakeven + Trailing + Pullback + Fake Breakout + ATR
"""

import os, time, threading
import ccxt
import pandas as pd
import requests as req
import telebot
from supabase import create_client

# ─── CONFIG ───
TELE_TOKEN   = os.getenv("TELE_TOKEN","")
CHAT_ID      = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API   = os.getenv("BITGET_API","")
BITGET_SEC   = os.getenv("BITGET_SEC","")
BITGET_PASS  = os.getenv("BITGET_PASS","")
SUPA_URL     = os.getenv("SUPABASE_URL","")
SUPA_KEY     = os.getenv("SUPABASE_KEY","")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY","")

# ─── RİSK ───
LEVERAGE      = 5
MARGIN        = 10.0
TP1_PCT       = 0.015   # %1.5 → %50 kapat + breakeven
TP2_PCT       = 0.025   # %2.5 → %25 kapat
TP3_PCT       = 0.040   # %4.0 → kalanı kapat
SL_PCT        = 0.020   # %2 stop loss
TRAIL_PCT     = 0.010   # Trailing %1 mesafe
MAX_OPEN      = 3
SCAN_INTERVAL = 30

# ─── FİLTRELER ───
MIN_VOLUME_RATIO = 1.5
MIN_MOMENTUM     = 0.3
MIN_RSI          = 40
MAX_RSI          = 72
AI_MIN_SCORE     = 60
MIN_QUOTE_VOL    = 5_000_000

# ─── KARA LİSTE ───
BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","MU","NVDA","TSLA","AAPL",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","FTM",
}

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: print(f"[TG] {e}")

# ─── SUPABASE ───
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        print("[SUPA] Bağlantı OK")
    except Exception as e: print(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try: supa.table("trades").insert(data).execute()
    except Exception as e: print(f"[SAVE] {e}")

def load_ai_data(symbol):
    if not supa: return pd.DataFrame()
    try:
        r = supa.table("trades").select("*").eq("symbol", symbol).execute()
        rows = []
        for rec in r.data or []:
            try:
                rows.append({
                    "momentum":     float(rec.get("momentum") or 0),
                    "volume_ratio": float(rec.get("volume_ratio") or 0),
                    "rsi":          float(rec.get("rsi") or 50),
                    "win":          1 if float(rec.get("pnl") or 0) > 0 else 0,
                })
            except: pass
        return pd.DataFrame(rows)
    except: return pd.DataFrame()

# ─── EXCHANGE ───
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})
_last = 0

def safe_api(func, *args, **kwargs):
    global _last
    for i in range(4):
        try:
            w = 0.6 - (time.time() - _last)
            if w > 0: time.sleep(w)
            _last = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            print(f"[API {i}] {e}")
            time.sleep(2)
    return None

# ─── STATE ───
positions = {}
pos_lock  = threading.Lock()

# ─── GÖSTERGELER ───
def calc_rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return float((100 - 100/(1+g/l.replace(0,0.001))).iloc[-1])

def calc_atr(df, n=14):
    h = df["h"]; l = df["l"]; c = df["c"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])

def calc_indicators(symbol):
    try:
        # 1m — giriş sinyali
        raw1 = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=100)
        if not raw1 or len(raw1) < 50: return None
        df1 = pd.DataFrame(raw1, columns=["t","o","h","l","c","v"])

        # 5m — trend teyidi
        raw5 = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=30)
        if not raw5: return None
        df5 = pd.DataFrame(raw5, columns=["t","o","h","l","c","v"])

        # 1h — büyük trend
        raw1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=50)
        trend_1h = "NEUTRAL"
        if raw1h and len(raw1h) >= 20:
            c1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])["c"]
            e20_1h = float(c1h.ewm(span=20).mean().iloc[-1])
            e50_1h = float(c1h.ewm(span=50).mean().iloc[-1])
            p1h    = float(c1h.iloc[-1])
            if p1h > e20_1h and e20_1h > e50_1h: trend_1h = "UP"
            elif p1h < e20_1h and e20_1h < e50_1h: trend_1h = "DOWN"

        c1 = df1["c"]; v1 = df1["v"]; c5 = df5["c"]

        price    = float(c1.iloc[-1])
        ema9     = float(c1.ewm(span=9).mean().iloc[-1])
        ema20    = float(c1.ewm(span=20).mean().iloc[-1])
        ema9_5   = float(c5.ewm(span=9).mean().iloc[-1])
        ema20_5  = float(c5.ewm(span=20).mean().iloc[-1])
        rsi_v    = calc_rsi(c1)
        atr      = calc_atr(df1)

        vol_avg   = float(v1.rolling(20).mean().iloc[-1])
        vol_ratio = float(v1.iloc[-1]) / max(vol_avg, 0.001)
        move_1    = (price - float(c1.iloc[-2])) / float(c1.iloc[-2]) * 100
        move_3    = (price - float(c1.iloc[-4])) / float(c1.iloc[-4]) * 100
        momentum  = abs(move_3)
        volatility= (float(df1["h"].iloc[-1]) - float(df1["l"].iloc[-1])) / price * 100

        # Pullback filtresi — son 10 barda en yüksek/düşük
        high10 = float(c1.tail(10).max())
        low10  = float(c1.tail(10).min())
        avg5   = float(c1.tail(5).mean())

        # Fake breakout filtresi — son 3 barda zirve yapıp geri dönmüş mü?
        last3_high = float(c1.tail(3).max())
        last3_low  = float(c1.tail(3).min())
        prev_high  = float(c1.tail(10).head(7).max())
        prev_low   = float(c1.tail(10).head(7).min())
        # Sahte breakout: son 3 bar önceki zirveyi kırdı ama geri döndü
        fake_up   = last3_high > prev_high and price < prev_high  # Yukarı kırdı geri geldi
        fake_down = last3_low  < prev_low  and price > prev_low   # Aşağı kırdı geri geldi

        return {
            "symbol": symbol, "price": price,
            "ema9": ema9, "ema20": ema20,
            "ema9_5": ema9_5, "ema20_5": ema20_5,
            "trend_1h": trend_1h, "rsi": rsi_v, "atr": atr,
            "vol_ratio": vol_ratio, "move_1": move_1,
            "move_3": move_3, "momentum": momentum,
            "volatility": volatility, "avg5": avg5,
            "high10": high10, "low10": low10,
            "fake_up": fake_up, "fake_down": fake_down,
        }
    except Exception as e:
        print(f"[IND {symbol}] {e}")
        return None

# ─── SİNYAL ───
def get_signal(ind):
    p    = ind["price"]
    e9   = ind["ema9"];   e20  = ind["ema20"]
    e9_5 = ind["ema9_5"]; e20_5= ind["ema20_5"]
    t1h  = ind["trend_1h"]; rsi = ind["rsi"]
    vr   = ind["vol_ratio"]; m1 = ind["move_1"]
    mom  = ind["momentum"]; avg5 = ind["avg5"]
    h10  = ind["high10"]; l10 = ind["low10"]
    atr  = ind["atr"]

    # Temel filtreler
    if vr  < MIN_VOLUME_RATIO: return None
    if mom < MIN_MOMENTUM:     return None
    if rsi < MIN_RSI:          return None
    if rsi > MAX_RSI:          return None

    # ATR filtresi — çok düşük volatilite = sıkışma, sinyal güvenilmez
    if atr / p * 100 < 0.05: return None

    # LONG
    if (p > e20 and e9 > e20          # 1m trend yukarı
            and e9_5 > e20_5          # 5m trend yukarı
            and m1 > 0                # son bar yeşil
            and p >= avg5             # sahte breakout değil
            and p <= h10 * 0.999      # tepede değil (pullback)
            and not ind["fake_up"]    # sahte yukarı kırılma değil
            and t1h != "DOWN"):       # 1h düşüş değil
        return "LONG"

    # SHORT
    if (p < e20 and e9 < e20
            and e9_5 < e20_5
            and m1 < -0.2
            and p <= avg5
            and p >= l10 * 1.001      # dipte değil (pullback)
            and not ind["fake_down"]  # sahte aşağı kırılma değil
            and vr >= 2.0
            and t1h == "DOWN"):
        return "SHORT"

    return None

# ─── AI SKOR ───
def ai_score(symbol, ind):
    try:
        df = load_ai_data(symbol)
        if df is None or len(df) < 20: return 65
        mask = (
            (df["volume_ratio"] >= ind["vol_ratio"] * 0.7) &
            (df["volume_ratio"] <= ind["vol_ratio"] * 1.3) &
            (df["momentum"]     >= ind["momentum"]  * 0.5)
        )
        sim = df[mask]
        if len(sim) < 5: return 65
        wr = sim["win"].mean() * 100
        bonus = 0
        if ind["vol_ratio"] >= 3.0: bonus += 10
        if ind["momentum"]  >= 1.5: bonus += 5
        if ind["rsi"] >= 55:        bonus += 5
        return min(95, int(wr + bonus))
    except: return 65

# ─── GPT KARAR ───
def gpt_karar(symbol, signal, ind):
    if not OPENAI_KEY:
        return True, "GPT yok"
    try:
        sym = symbol.split("/")[0]
        prompt = f"""Kripto futures trading uzmanısın.

Coin: {sym}/USDT
Sinyal: {signal}
1h Trend: {ind['trend_1h']}
RSI: {ind['rsi']:.1f}
Hacim: {ind['vol_ratio']:.1f}x
Momentum (3 bar): {ind['move_3']:+.2f}%
Son bar: {ind['move_1']:+.2f}%
Volatilite: {ind['volatility']:.2f}%
Sahte kırılım: {'VAR' if (signal=='LONG' and ind['fake_up']) or (signal=='SHORT' and ind['fake_down']) else 'YOK'}

Sadece:
GİR — [1 cümle neden]
veya
PAS — [1 cümle neden]"""

        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "max_tokens": 80,
                  "temperature": 0.2,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=10)

        if r.status_code == 200:
            yanit = r.json()["choices"][0]["message"]["content"].strip()
            gir = yanit.upper().startswith("GİR") or yanit.upper().startswith("GIR")
            return gir, yanit
    except Exception as e:
        print(f"[GPT] {e}")
    return True, "GPT hata"

# ─── TARAMA ───
def scan_coins():
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return []
        active = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith("/USDT:USDT"): continue
            sym_name = symbol.split("/")[0]
            if sym_name in BLACKLIST: continue
            if ticker.get("quoteVolume", 0) < MIN_QUOTE_VOL: continue
            price = ticker.get("last", 0) or 0
            if price > 500: continue  # hisse tokenları
            pct = abs(ticker.get("percentage", 0) or 0)
            if pct < 0.3: continue
            active.append({
                "symbol": symbol,
                "volume": ticker.get("quoteVolume", 0),
                "change": ticker.get("percentage", 0),
            })
        active.sort(key=lambda x: x["volume"], reverse=True)
        print(f"[SCAN] {len(active)} coin aktif")
        return active[:60]
    except Exception as e:
        print(f"[SCAN] {e}")
        return []

# ─── KISMİ KAPAT ───
def kismi_kapat(symbol, pos, oran, sebep):
    try:
        ps = safe_api(exchange.fetch_positions, [symbol])
        size = 0
        if ps:
            for p in ps:
                sz = abs(float(p.get("contracts") or p.get("size") or 0))
                if sz > 0: size = sz; break
        if size <= 0: return
        miktar = float(exchange.amount_to_precision(symbol, size * oran))
        if miktar <= 0: return
        side = "sell" if pos["signal"]=="LONG" else "buy"
        safe_api(exchange.create_market_order, symbol, side, miktar,
                 params={"reduceOnly": True})
        t = safe_api(exchange.fetch_ticker, symbol)
        if t:
            cp = t["last"]
            if pos["signal"] == "LONG":
                pnl = (cp-pos["entry"])/pos["entry"]*MARGIN*LEVERAGE*oran
            else:
                pnl = (pos["entry"]-cp)/pos["entry"]*MARGIN*LEVERAGE*oran
            tg(f"🟡 {symbol.split('/')[0]} {sebep}\n+{pnl:.2f} USDT ({int(oran*100)}% kapatıldı)")
    except Exception as e:
        print(f"[KISMI {symbol}] {e}")

# ─── POZİSYON AÇ ───
def open_position(symbol, signal, ind, score, gpt_yorum):
    with pos_lock:
        if symbol in positions: return
        if len(positions) >= MAX_OPEN: return
    try:
        safe_api(exchange.set_leverage, LEVERAGE, symbol)
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t: return
        price  = t["last"]
        amount = float(exchange.amount_to_precision(
            symbol, (MARGIN * LEVERAGE) / price))
        side  = "buy" if signal == "LONG" else "sell"
        order = safe_api(exchange.create_market_order, symbol, side, amount)
        if not order: return
        entry = float(order.get("average") or price)

        if signal == "LONG":
            tp1 = round(entry*(1+TP1_PCT), 8)
            tp2 = round(entry*(1+TP2_PCT), 8)
            tp3 = round(entry*(1+TP3_PCT), 8)
            sl  = round(entry*(1-SL_PCT),  8)
        else:
            tp1 = round(entry*(1-TP1_PCT), 8)
            tp2 = round(entry*(1-TP2_PCT), 8)
            tp3 = round(entry*(1-TP3_PCT), 8)
            sl  = round(entry*(1+SL_PCT),  8)

        with pos_lock:
            positions[symbol] = {
                "signal": signal, "entry": entry,
                "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
                "tp1_done": False, "tp2_done": False,
                "max_pnl": 0.0, "trail_active": False,
                "score": score, "ind": ind,
                "open_time": time.time(),
            }

        sym = symbol.split("/")[0]
        tg(
            f"🚀 {sym} {signal} AÇILDI\n"
            f"Giriş: {entry:.6f}\n"
            f"TP1: {tp1:.6f} (+%{TP1_PCT*100:.1f}) → %50\n"
            f"TP2: {tp2:.6f} (+%{TP2_PCT*100:.1f}) → %25\n"
            f"TP3: {tp3:.6f} (+%{TP3_PCT*100:.1f}) → kalan\n"
            f"SL:  {sl:.6f} (-%{SL_PCT*100:.0f})\n"
            f"Trend:{ind['trend_1h']} RSI:{ind['rsi']:.0f} Hacim:{ind['vol_ratio']:.1f}x\n"
            f"🤖 {gpt_yorum}"
        )
    except Exception as e:
        print(f"[OPEN {symbol}] {e}")

# ─── POZİSYON KAPAT ───
def close_position(symbol, reason):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return
    try:
        ps = safe_api(exchange.fetch_positions, [symbol])
        size = 0
        if ps:
            for p in ps:
                sz = abs(float(p.get("contracts") or p.get("size") or 0))
                if sz > 0: size = sz; break
        if size > 0:
            side = "sell" if pos["signal"]=="LONG" else "buy"
            safe_api(exchange.create_market_order, symbol, side, size,
                     params={"reduceOnly": True})
        t = safe_api(exchange.fetch_ticker, symbol)
        pnl = 0.0
        if t:
            cp = t["last"]
            if pos["signal"] == "LONG":
                pnl = (cp-pos["entry"])/pos["entry"]*MARGIN*LEVERAGE
            else:
                pnl = (pos["entry"]-cp)/pos["entry"]*MARGIN*LEVERAGE
        ind = pos.get("ind", {})
        save_trade({
            "symbol": symbol, "signal": pos["signal"],
            "pnl": round(pnl,4), "ai_score": pos["score"],
            "momentum":     ind.get("momentum", 0),
            "volume_ratio": ind.get("vol_ratio", 0),
            "volatility":   ind.get("volatility", 0),
            "rsi":          ind.get("rsi", 0),
            "move_1":       ind.get("move_1", 0),
            "move_3":       ind.get("move_3", 0),
        })
        sym  = symbol.split("/")[0]
        icon = "🟢" if pnl >= 0 else "🔴"
        tg(f"{icon} {sym} KAPANDI\n{reason}\nPnL: {pnl:+.2f} USDT")
    except Exception as e:
        print(f"[CLOSE {symbol}] {e}")

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(5)
        try:
            with pos_lock:
                syms = list(positions.keys())

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price  = t["last"]
                entry  = pos["entry"]
                signal = pos["signal"]

                if signal == "LONG":
                    pnl_pct = (price-entry)/entry*100
                else:
                    pnl_pct = (entry-price)/entry*100
                pnl = pnl_pct/100*MARGIN*LEVERAGE

                if pnl > pos["max_pnl"]:
                    pos["max_pnl"] = pnl
                max_pnl = pos["max_pnl"]

                # ─── STOP LOSS ───
                if pnl_pct <= -SL_PCT*100:
                    close_position(symbol, f"STOP LOSS -%{SL_PCT*100:.0f}")
                    continue

                # ─── TP1 +%1.5 → %50 kapat + breakeven ───
                if not pos["tp1_done"] and pnl_pct >= TP1_PCT*100:
                    kismi_kapat(symbol, pos, 0.5, f"TP1 +%{TP1_PCT*100:.1f}")
                    pos["tp1_done"] = True
                    pos["sl"] = entry  # SL breakeven'e çek
                    continue

                # ─── TP2 +%2.5 → %25 kapat ───
                if pos["tp1_done"] and not pos["tp2_done"] and pnl_pct >= TP2_PCT*100:
                    kismi_kapat(symbol, pos, 0.5, f"TP2 +%{TP2_PCT*100:.1f}")
                    pos["tp2_done"] = True
                    pos["trail_active"] = True  # Trailing başlat
                    continue

                # ─── TP3 +%4 → kalanı kapat ───
                if pos["tp2_done"] and pnl_pct >= TP3_PCT*100:
                    close_position(symbol, f"TP3 +%{TP3_PCT*100:.1f} 🎯")
                    continue

                # ─── BREAKEVEN KORUMA (TP1 sonrası) ───
                if pos["tp1_done"] and pnl_pct <= 0:
                    close_position(symbol, "BREAKEVEN KORUMA")
                    continue

                # ─── DYNAMIC TRAILING STOP (TP2 sonrası) ───
                if pos["trail_active"]:
                    trail_floor = max_pnl - TRAIL_PCT*100
                    if pnl_pct <= trail_floor:
                        close_position(symbol, f"TRAILING +{pnl:.2f} 🚀")
                        continue

                # ─── ZAMAN AŞIMI 60dk ───
                if time.time() - pos["open_time"] > 60*60:
                    close_position(symbol, "ZAMAN AŞIMI 60dk")
                    continue

        except Exception as e:
            print(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    while True:
        try:
            with pos_lock:
                open_count = len(positions)
                open_syms  = set(positions.keys())

            if open_count >= MAX_OPEN:
                time.sleep(10)
                continue

            active = scan_coins()
            if not active:
                time.sleep(SCAN_INTERVAL)
                continue

            for coin in active:
                symbol = coin["symbol"]
                if symbol in open_syms: continue
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break

                ind = calc_indicators(symbol)
                if not ind: continue

                signal = get_signal(ind)
                if not signal: continue

                score = ai_score(symbol, ind)
                if score < AI_MIN_SCORE:
                    print(f"[SKIP] {symbol.split('/')[0]} AI:%{score}")
                    continue

                gir, yorum = gpt_karar(symbol, signal, ind)
                sym = symbol.split("/")[0]
                print(f"[GPT] {sym} {signal} → {'GİR ✅' if gir else 'PAS ❌'} | {yorum}")

                if not gir: continue

                print(f"[SİNYAL] {sym} {signal} RSI={ind['rsi']:.0f} vol={ind['vol_ratio']:.1f}x trend={ind['trend_1h']}")
                open_position(symbol, signal, ind, score, yorum)
                time.sleep(2)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"[SCANNER] {e}")
            time.sleep(10)

# ─── HEALTH ───
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ─── KOMUTLAR ───
@bot.message_handler(commands=["durum","status"])
def cmd_durum(msg):
    with pos_lock:
        if not positions:
            bot.send_message(msg.chat.id, "📊 Açık pozisyon yok."); return
        lines = ["📊 AÇIK POZİSYONLAR\n"]
        for sym, pos in positions.items():
            t = safe_api(exchange.fetch_ticker, sym)
            if t:
                price = t["last"]
                pnl = (price-pos["entry"])/pos["entry"]*MARGIN*LEVERAGE if pos["signal"]=="LONG" else (pos["entry"]-price)/pos["entry"]*MARGIN*LEVERAGE
                tp1s = "✅" if pos["tp1_done"] else "⏳"
                tp2s = "✅" if pos["tp2_done"] else "⏳"
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} {pos['signal']}\n"
                    f"Giriş:{pos['entry']:.6f} → {price:.6f}\n"
                    f"PnL:{pnl:+.2f} USDT  TP1:{tp1s} TP2:{tp2s}\n"
                )
        bot.send_message(msg.chat.id, "\n".join(lines))

@bot.message_handler(commands=["kapat"])
def cmd_kapat(msg):
    text = msg.text.replace("/kapat","").strip().upper()
    if not text:
        bot.send_message(msg.chat.id, "Kullanım: /kapat SOL"); return
    symbol = f"{text}/USDT:USDT"
    with pos_lock:
        if symbol not in positions:
            bot.send_message(msg.chat.id, f"❌ {text} yok."); return
    close_position(symbol, "MANUEL KAPANIŞ")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock: syms = list(positions.keys())
    for s in syms: close_position(s, "MANUEL HEPSI KAPAT")

# ─── MAIN ───
if __name__ == "__main__":
    print("🚀 SADIK DYNAMIC SCANNER BOT v5 BAŞLIYOR...")
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=scanner_loop,  daemon=True).start()
    print("[OK] Health | Manage | Scanner")
    tg(
        "🚀 SADIK DYNAMIC SCANNER BOT v5\n\n"
        f"Kaldıraç: {LEVERAGE}x  Marjin: {MARGIN} USDT\n"
        f"TP1: +%{TP1_PCT*100:.1f} → %50 + breakeven\n"
        f"TP2: +%{TP2_PCT*100:.1f} → %25 + trailing\n"
        f"TP3: +%{TP3_PCT*100:.1f} → tam kapat\n"
        f"SL:  -%{SL_PCT*100:.0f}\n\n"
        "Filtreler:\n"
        "✅ 1h Trend filtresi\n"
        "✅ Pullback filtresi\n"
        "✅ Fake Breakout filtresi\n"
        "✅ ATR volatilite filtresi\n"
        "✅ GPT analizi\n\n"
        "/durum /kapat SOL /hepsikapat"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"[POLLING] {e}"); time.sleep(5)
