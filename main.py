#!/usr/bin/env python3
"""
SADIK DYNAMIC SCANNER BOT v4
Sabit coin listesi, pullback filtresi, TP1/2/3, trailing, GPT
"""

import os, time, threading
import ccxt
import pandas as pd
import requests as req
import telebot
from supabase import create_client

# ─── CONFIG ───
TELE_TOKEN    = os.getenv("TELE_TOKEN","")
CHAT_ID       = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API    = os.getenv("BITGET_API","")
BITGET_SEC    = os.getenv("BITGET_SEC","")
BITGET_PASS   = os.getenv("BITGET_PASS","")
SUPA_URL      = os.getenv("SUPABASE_URL","")
SUPA_KEY      = os.getenv("SUPABASE_KEY","")
OPENAI_KEY    = os.getenv("OPENAI_API_KEY","")
CG_KEY        = os.getenv("COINGLASS_API_KEY", os.getenv("COINGL_API_KEY",""))

# ─── RİSK ───
LEVERAGE      = 5
MARGIN        = 10.0
TP1_PCT       = 0.015   # %1.5 → %50 kapat, SL breakeven
TP2_PCT       = 0.025   # %2.5 → %25 kapat
TP3_PCT       = 0.040   # %4.0 → kalanı kapat
SL_PCT        = 0.020   # %2 stop loss
TRAIL_DIST    = 0.010   # Trailing mesafesi %1
MAX_OPEN      = 3
SCAN_INTERVAL = 40      # saniye

# ─── FİLTRELER ───
MIN_VOL_RATIO = 1.5     # Hacim artışı
MIN_RSI       = 40
MAX_RSI       = 68
MIN_MOMENTUM  = 0.2     # %0.2 hareket
PULLBACK_PCT  = 0.998   # Tepeden %0.2 aşağıda olmalı

# ─── SABİT KOİN LİSTESİ ───
# Hareketli, güvenilir, $50M+ günlük hacim
COINS = [
    "SOL/USDT:USDT",
    "DOGE/USDT:USDT",
    "PEPE/USDT:USDT",
    "WIF/USDT:USDT",
    "SUI/USDT:USDT",
    "APT/USDT:USDT",
    "INJ/USDT:USDT",
    "OP/USDT:USDT",
    "ARB/USDT:USDT",
    "LINK/USDT:USDT",
    "AVAX/USDT:USDT",
    "NEAR/USDT:USDT",
    "FTM/USDT:USDT",
    "ATOM/USDT:USDT",
    "DOT/USDT:USDT",
    "UNI/USDT:USDT",
    "AAVE/USDT:USDT",
    "LDO/USDT:USDT",
    "IMX/USDT:USDT",
    "SAND/USDT:USDT",
    "MANA/USDT:USDT",
    "GALA/USDT:USDT",
    "AXS/USDT:USDT",
    "CHZ/USDT:USDT",
    "MASK/USDT:USDT",
]

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
        print("[SUPA] OK")
    except Exception as e:
        print(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try: supa.table("trades").insert(data).execute()
    except Exception as e: print(f"[SAVE] {e}")

def load_history(symbol):
    if not supa: return pd.DataFrame()
    try:
        r = supa.table("trades").select("*").eq("symbol", symbol).execute()
        rows = []
        for rec in r.data or []:
            try:
                rows.append({
                    "vol_ratio": float(rec.get("volume_ratio") or 0),
                    "rsi":       float(rec.get("rsi") or 50),
                    "momentum":  float(rec.get("momentum") or 0),
                    "win":       1 if float(rec.get("pnl") or 0) > 0 else 0,
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
_last_api = 0

def safe_api(func, *args, **kwargs):
    global _last_api
    for i in range(4):
        try:
            w = 0.7 - (time.time() - _last_api)
            if w > 0: time.sleep(w)
            _last_api = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(15)
        except Exception as e:
            print(f"[API {i}] {e}")
            time.sleep(3)
    return None

# ─── STATE ───
positions = {}
pos_lock  = threading.Lock()

# ─── GÖSTERGELER ───
def rsi(closes, n=14):
    d = closes.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return float((100 - 100/(1+g/l.replace(0,0.001))).iloc[-1])

def indicators(symbol):
    try:
        # 3m ana timeframe — hızlı sinyal
        raw3 = safe_api(exchange.fetch_ohlcv, symbol, "3m", limit=60)
        if not raw3 or len(raw3) < 30: return None
        df3 = pd.DataFrame(raw3, columns=["t","o","h","l","c","v"])
        c3 = df3["c"]; v3 = df3["v"]

        # 15m trend teyidi
        raw15 = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=30)
        if not raw15: return None
        df15 = pd.DataFrame(raw15, columns=["t","o","h","l","c","v"])
        c15 = df15["c"]

        price  = float(c3.iloc[-1])
        ema9   = float(c3.ewm(span=9).mean().iloc[-1])
        ema21  = float(c3.ewm(span=21).mean().iloc[-1])
        ema50  = float(c3.ewm(span=50).mean().iloc[-1])
        rsi_v  = rsi(c3)

        # 15m trend
        ema9_15  = float(c15.ewm(span=9).mean().iloc[-1])
        ema21_15 = float(c15.ewm(span=21).mean().iloc[-1])

        vol_avg   = float(v3.rolling(20).mean().iloc[-1])
        vol_ratio = float(v3.iloc[-1]) / max(vol_avg, 0.001)
        move_1    = (price - float(c3.iloc[-2])) / float(c3.iloc[-2]) * 100
        move_5    = (price - float(c3.iloc[-6])) / float(c3.iloc[-6]) * 100
        momentum  = abs(move_5)
        high10    = float(c3.tail(10).max())
        low10     = float(c3.tail(10).min())

        # 1h büyük trend
        raw1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=30)
        trend_1h = "NEUTRAL"
        if raw1h and len(raw1h) >= 20:
            c1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])["c"]
            e20 = float(c1h.ewm(span=20).mean().iloc[-1])
            p1h = float(c1h.iloc[-1])
            if p1h > e20: trend_1h = "UP"
            elif p1h < e20: trend_1h = "DOWN"

        return {
            "symbol": symbol, "price": price,
            "ema9": ema9, "ema21": ema21, "ema50": ema50,
            "ema9_15": ema9_15, "ema21_15": ema21_15,
            "rsi": rsi_v, "vol_ratio": vol_ratio,
            "move_1": move_1, "move_5": move_5,
            "momentum": momentum, "trend_1h": trend_1h,
            "high10": high10, "low10": low10,
        }
    except Exception as e:
        print(f"[IND {symbol}] {e}")
        return None

# ─── SİNYAL ───
def signal(ind):
    p      = ind["price"]
    e9     = ind["ema9"]
    e21    = ind["ema21"]
    e50    = ind["ema50"]
    e9_15  = ind["ema9_15"]
    e21_15 = ind["ema21_15"]
    rsi_v  = ind["rsi"]
    vr     = ind["vol_ratio"]
    m1     = ind["move_1"]
    mom    = ind["momentum"]
    t1h    = ind["trend_1h"]
    h10    = ind["high10"]
    l10    = ind["low10"]

    if vr    < MIN_VOL_RATIO: return None
    if mom   < MIN_MOMENTUM:  return None
    if rsi_v < MIN_RSI:       return None
    if rsi_v > MAX_RSI:       return None

    # LONG — 3m trend + 15m teyidi + pullback + 1h filtre
    if (e9 > e21 > e50              # 3m EMA hizalaması
            and e9_15 > e21_15      # 15m de yukarı
            and p > e21             # fiyat EMA21 üstünde
            and p <= h10 * PULLBACK_PCT  # tepede değil
            and m1 > 0              # son bar yeşil
            and t1h != "DOWN"):     # 1h düşüş değil
        return "LONG"

    # SHORT — 3m + 15m + pullback + 1h
    if (e9 < e21 < e50
            and e9_15 < e21_15      # 15m de aşağı
            and p < e21
            and p >= l10 * (2-PULLBACK_PCT)
            and m1 < 0
            and t1h != "UP"):
        return "SHORT"

    return None

# ─── AI SKOR ───
def ai_skor(symbol, ind):
    try:
        df = load_history(symbol)
        if df is None or len(df) < 15: return 65
        mask = (
            (df["vol_ratio"] >= ind["vol_ratio"] * 0.6) &
            (df["vol_ratio"] <= ind["vol_ratio"] * 1.4)
        )
        sim = df[mask]
        if len(sim) < 3: return 65
        win_rate = sim["win"].mean() * 100
        bonus = 5 if ind["vol_ratio"] >= 2.5 else 0
        bonus += 5 if ind["momentum"] >= 0.5 else 0
        return min(95, int(win_rate + bonus))
    except: return 65

# ─── GPT KARAR ───
def gpt_karar(symbol, sig, ind):
    if not OPENAI_KEY:
        return True, "GPT yok — varsayılan GİR"
    try:
        sym = symbol.split("/")[0]
        prompt = f"""Kripto futures uzmanısın. Bu işleme girmeli miyim?

Coin: {sym}/USDT
Sinyal: {sig}
1h Trend: {ind['trend_1h']}
EMA9 {'>' if ind['ema9'] > ind['ema21'] else '<'} EMA21 {'>' if ind['ema21'] > ind['ema50'] else '<'} EMA50
RSI: {ind['rsi']:.1f}
Hacim: {ind['vol_ratio']:.1f}x normal
Momentum (5 bar): {ind['move_5']:+.2f}%
Son bar: {ind['move_1']:+.2f}%

Sadece şu formatta cevap ver:
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
    return True, "GPT hata — varsayılan GİR"

# ─── GPT TAKİP ───
def gpt_takip(symbol, sig, ind, pnl_pct):
    if not OPENAI_KEY: return True, "GPT yok"
    try:
        sym = symbol.split("/")[0]
        prompt = f"""Açık pozisyon takip ediyorum.

Coin: {sym}/USDT — {sig}
PnL: {pnl_pct:+.2f}%
RSI: {ind['rsi']:.1f}
Momentum: {ind['move_5']:+.2f}%
1h Trend: {ind['trend_1h']}

Sadece:
DEVAM — [neden]
veya
KAPAT — [neden]"""

        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "max_tokens": 60,
                  "temperature": 0.2,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=8)

        if r.status_code == 200:
            yanit = r.json()["choices"][0]["message"]["content"].strip()
            return yanit.upper().startswith("DEVAM"), yanit
    except Exception as e:
        print(f"[GPT-TAK] {e}")
    return True, "GPT hata"

# ─── POZİSYON AÇ ───
def ac(symbol, sig, ind, skor, yorum):
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
        side  = "buy" if sig == "LONG" else "sell"
        order = safe_api(exchange.create_market_order, symbol, side, amount)
        if not order: return
        entry = float(order.get("average") or price)

        if sig == "LONG":
            tp1 = round(entry*(1+TP1_PCT),8)
            tp2 = round(entry*(1+TP2_PCT),8)
            tp3 = round(entry*(1+TP3_PCT),8)
            sl  = round(entry*(1-SL_PCT), 8)
        else:
            tp1 = round(entry*(1-TP1_PCT),8)
            tp2 = round(entry*(1-TP2_PCT),8)
            tp3 = round(entry*(1-TP3_PCT),8)
            sl  = round(entry*(1+SL_PCT), 8)

        with pos_lock:
            positions[symbol] = {
                "sig": sig, "entry": entry,
                "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
                "tp1_done": False, "tp2_done": False,
                "contracts": amount,
                "max_pnl": 0.0, "trail_sl": None,
                "skor": skor, "ind": ind,
                "open_time": time.time(),
                "last_gpt": time.time(),
            }

        sym = symbol.split("/")[0]
        tg(
            f"🚀 {sym} {sig} AÇILDI\n"
            f"Giriş: {entry:.6f}\n"
            f"TP1: {tp1:.6f} (+%{TP1_PCT*100:.1f})\n"
            f"TP2: {tp2:.6f} (+%{TP2_PCT*100:.1f})\n"
            f"TP3: {tp3:.6f} (+%{TP3_PCT*100:.1f})\n"
            f"SL:  {sl:.6f} (-%{SL_PCT*100:.0f})\n"
            f"RSI:{ind['rsi']:.0f}  Hacim:{ind['vol_ratio']:.1f}x  Trend:{ind['trend_1h']}\n"
            f"🤖 {yorum}"
        )
    except Exception as e:
        print(f"[AC {symbol}] {e}")

# ─── POZİSYON KAPAT ───
def kapat(symbol, neden):
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
            side = "sell" if pos["sig"]=="LONG" else "buy"
            safe_api(exchange.create_market_order, symbol, side, size,
                     params={"reduceOnly": True})
        t = safe_api(exchange.fetch_ticker, symbol)
        pnl = 0.0
        if t:
            cp = t["last"]
            pnl = (cp-pos["entry"])/pos["entry"]*MARGIN*LEVERAGE if pos["sig"]=="LONG" else (pos["entry"]-cp)/pos["entry"]*MARGIN*LEVERAGE
        ind = pos.get("ind", {})
        save_trade({
            "symbol": symbol, "signal": pos["sig"],
            "pnl": round(pnl,4), "ai_score": pos["skor"],
            "momentum": ind.get("momentum",0),
            "volume_ratio": ind.get("vol_ratio",0),
            "volatility": 0,
            "rsi": ind.get("rsi",0),
            "move_1": ind.get("move_1",0),
            "move_3": ind.get("move_5",0),
        })
        sym = symbol.split("/")[0]
        icon = "🟢" if pnl>=0 else "🔴"
        tg(f"{icon} {sym} KAPANDI\n{neden}\nPnL: {pnl:+.2f} USDT")
    except Exception as e:
        print(f"[KAPAT {symbol}] {e}")

# ─── KISMİ KAPAT ───
def kismi_kapat(symbol, pos, oran, neden):
    try:
        ps = safe_api(exchange.fetch_positions, [symbol])
        size = 0
        if ps:
            for p in ps:
                sz = abs(float(p.get("contracts") or p.get("size") or 0))
                if sz > 0: size = sz; break
        if size <= 0: return
        kismi = float(exchange.amount_to_precision(symbol, size * oran))
        if kismi <= 0: return
        side = "sell" if pos["sig"]=="LONG" else "buy"
        safe_api(exchange.create_market_order, symbol, side, kismi,
                 params={"reduceOnly": True})
        sym = symbol.split("/")[0]
        t = safe_api(exchange.fetch_ticker, symbol)
        if t:
            cp = t["last"]
            pnl_kismi = (cp-pos["entry"])/pos["entry"]*MARGIN*LEVERAGE*oran if pos["sig"]=="LONG" else (pos["entry"]-cp)/pos["entry"]*MARGIN*LEVERAGE*oran
            tg(f"🟡 {sym} {neden}\n+{pnl_kismi:.2f} USDT ({int(oran*100)}% kapatıldı)")
    except Exception as e:
        print(f"[KISMI {symbol}] {e}")

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(8)
        try:
            with pos_lock:
                syms = list(positions.keys())

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = t["last"]
                entry = pos["entry"]
                sig   = pos["sig"]

                pnl_pct = (price-entry)/entry*100 if sig=="LONG" else (entry-price)/entry*100
                pnl     = pnl_pct/100*MARGIN*LEVERAGE

                if pnl > pos["max_pnl"]:
                    pos["max_pnl"] = pnl

                # ─── SL ───
                if pnl_pct <= -SL_PCT*100:
                    kapat(symbol, f"STOP LOSS -%{SL_PCT*100:.0f}")
                    continue

                # ─── TP1 ─── %1.5 → %50 kapat, breakeven
                if not pos["tp1_done"] and pnl_pct >= TP1_PCT*100:
                    kismi_kapat(symbol, pos, 0.5, f"TP1 +%{TP1_PCT*100:.1f}")
                    pos["tp1_done"] = True
                    # SL breakeven'e çek
                    pos["sl"] = entry
                    continue

                # ─── TP2 ─── %2.5 → %25 kapat
                if pos["tp1_done"] and not pos["tp2_done"] and pnl_pct >= TP2_PCT*100:
                    kismi_kapat(symbol, pos, 0.5, f"TP2 +%{TP2_PCT*100:.1f}")
                    pos["tp2_done"] = True
                    continue

                # ─── TP3 ─── %4 → kalanı kapat
                if pos["tp2_done"] and pnl_pct >= TP3_PCT*100:
                    kapat(symbol, f"TP3 +%{TP3_PCT*100:.1f} 🎯")
                    continue

                # ─── BREAKEVEN KORUMA ───
                if pos["tp1_done"] and pnl_pct <= 0:
                    kapat(symbol, "BREAKEVEN KORUMA")
                    continue

                # ─── TRAILING STOP ─── TP2 sonrası
                if pos["tp2_done"]:
                    if pos["trail_sl"] is None:
                        pos["trail_sl"] = pnl_pct - TRAIL_DIST*100
                    else:
                        if pnl_pct > pos["trail_sl"] + TRAIL_DIST*100:
                            pos["trail_sl"] = pnl_pct - TRAIL_DIST*100
                        if pnl_pct <= pos["trail_sl"]:
                            kapat(symbol, f"TRAILING +{pnl:.2f} 🚀")
                            continue

                # ─── ZAMAN AŞIMI 60dk ───
                if time.time() - pos["open_time"] > 60*60:
                    kapat(symbol, "ZAMAN AŞIMI 60dk")
                    continue

                # ─── GPT TAKİP 10dk'da bir ───
                if time.time() - pos.get("last_gpt",0) > 600:
                    try:
                        ind = pos.get("ind",{})
                        ind["rsi"] = rsi(pd.Series([entry]*14 + [price]))
                        devam, yorum = gpt_takip(symbol, sig, ind, pnl_pct)
                        pos["last_gpt"] = time.time()
                        print(f"[GPT-TAK] {symbol.split('/')[0]} → {'DEVAM' if devam else 'KAPAT'}")
                        if not devam and pnl_pct < -0.5:  # Sadece zarardaysa kapat
                            kapat(symbol, f"GPT: {yorum[:40]}")
                            continue
                    except: pass

        except Exception as e:
            print(f"[MANAGE] {e}")

def get_coins():
    """Sabit liste + $10M+ hacimli dinamik coinler"""
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers:
            return COINS

        dinamik = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith("/USDT:USDT"): continue
            if symbol in COINS: continue  # Zaten sabit listede
            sym_name = symbol.split("/")[0]
            # Kara liste
            if any(bl in sym_name for bl in ["BANANAS","BSB","JCT","MEGA"]): continue
            # Hisse tokenı değil
            price = ticker.get("last", 0) or 0
            if price > 50: continue
            # Min $10M hacim
            if ticker.get("quoteVolume", 0) < 10_000_000: continue
            # Hareket var mı
            pct = abs(ticker.get("percentage", 0) or 0)
            if pct < 0.5: continue
            dinamik.append(symbol)

        # Hacme göre sırala, top 20 ekle
        tum = list(COINS) + dinamik[:20]
        print(f"[SCAN] {len(COINS)} sabit + {len(dinamik[:20])} dinamik = {len(tum)} coin")
        return tum
    except Exception as e:
        print(f"[GET_COINS] {e}")
        return COINS
    while True:
        try:
            with pos_lock:
                open_syms = set(positions.keys())
                open_cnt  = len(positions)

            if open_cnt >= MAX_OPEN:
                time.sleep(15)
                continue

            coins = get_coins()

            for symbol in coins:
                if symbol in open_syms: continue
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break

                ind = indicators(symbol)
                if not ind: continue

                sig = signal(ind)
                if not sig: continue

                skor = ai_skor(symbol, ind)
                sym  = symbol.split("/")[0]
                print(f"[SİNYAL] {sym} {sig} RSI={ind['rsi']:.0f} vol={ind['vol_ratio']:.1f}x trend={ind['trend_1h']}")

                gir, yorum = gpt_karar(symbol, sig, ind)
                print(f"[GPT] {sym} → {'GİR ✅' if gir else 'PAS ❌'} | {yorum}")

                if gir:
                    ac(symbol, sig, ind, skor, yorum)

                time.sleep(2)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"[SCANNER] {e}")
            time.sleep(10)

# ─── HEALTH ───
def health():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# ─── KOMUTLAR ───
@bot.message_handler(commands=["durum","status"])
def cmd_durum(msg):
    with pos_lock:
        if not positions:
            bot.send_message(msg.chat.id,"📊 Açık pozisyon yok."); return
        lines = ["📊 AÇIK POZİSYONLAR\n"]
        for sym,pos in positions.items():
            t = safe_api(exchange.fetch_ticker,sym)
            if t:
                price = t["last"]
                pnl = (price-pos["entry"])/pos["entry"]*MARGIN*LEVERAGE if pos["sig"]=="LONG" else (pos["entry"]-price)/pos["entry"]*MARGIN*LEVERAGE
                tp1s = "✅" if pos["tp1_done"] else "⏳"
                tp2s = "✅" if pos["tp2_done"] else "⏳"
                lines.append(f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} {pos['sig']}\nGiriş:{pos['entry']:.6f} → {price:.6f}\nPnL:{pnl:+.2f} USDT  TP1:{tp1s} TP2:{tp2s}\n")
        bot.send_message(msg.chat.id,"\n".join(lines))

@bot.message_handler(commands=["kapat"])
def cmd_kapat(msg):
    text = msg.text.replace("/kapat","").strip().upper()
    if not text:
        bot.send_message(msg.chat.id,"Kullanım: /kapat SOL"); return
    sym = f"{text}/USDT:USDT"
    with pos_lock:
        if sym not in positions:
            bot.send_message(msg.chat.id,f"❌ {text} yok."); return
    kapat(sym,"MANUEL KAPANIŞ")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock: syms = list(positions.keys())
    for s in syms: kapat(s,"MANUEL HEPSI KAPAT")

# ─── MAIN ───
if __name__ == "__main__":
    print("🚀 SADIK BOT v4 BAŞLIYOR...")
    threading.Thread(target=health,       daemon=True).start()
    threading.Thread(target=manage_loop,  daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    print("[OK] Health | Manage | Scanner")
    tg(
        "🚀 SADIK DYNAMIC SCANNER BOT v4\n\n"
        f"Kaldıraç: {LEVERAGE}x  Marjin: {MARGIN} USDT\n"
        f"TP1: +%{TP1_PCT*100:.1f} → %50 kapat + breakeven\n"
        f"TP2: +%{TP2_PCT*100:.1f} → %25 kapat\n"
        f"TP3: +%{TP3_PCT*100:.1f} → tam kapat\n"
        f"SL:  -%{SL_PCT*100:.0f}\n"
        f"Trailing: TP2 sonrası aktif\n"
        f"GPT: GİR/PAS + 10dk takip\n"
        f"{len(COINS)} güvenilir coin\n\n"
        "/durum /kapat SOL /hepsikapat"
    )
    while True:
        try: bot.infinity_polling(timeout=30,long_polling_timeout=30)
        except Exception as e:
            print(f"[POLLING] {e}"); time.sleep(5)
