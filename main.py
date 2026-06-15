#!/usr/bin/env python3
"""
SADIK DYNAMIC SCANNER BOT v3
CoinGlass + GPT + 3 dakika onay + canlı takip
"""

import os, time, threading
import ccxt
import pandas as pd
import requests as req
import telebot
from supabase import create_client

# ─── CONFIG ───
TELE_TOKEN      = os.getenv("TELE_TOKEN","")
CHAT_ID         = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API      = os.getenv("BITGET_API","")
BITGET_SEC      = os.getenv("BITGET_SEC","")
BITGET_PASS     = os.getenv("BITGET_PASS","")
SUPA_URL        = os.getenv("SUPABASE_URL","")
SUPA_KEY        = os.getenv("SUPABASE_KEY","")
OPENAI_KEY      = os.getenv("OPENAI_API_KEY","")
COINGLASS_KEY   = os.getenv("COINGLASS_API_KEY", os.getenv("COINGL_API_KEY",""))

# Risk ayarları
LEVERAGE        = 5
MARGIN          = 10.0
TP_PCT          = 0.03    # %3 TP
SL_PCT          = 0.02    # %2 SL
MAX_OPEN        = 3
SCAN_INTERVAL   = 30
CONFIRM_WAIT    = 180     # 3 dakika bekleme — sahte pump filtresi

# Filtreler
MIN_VOLUME_RATIO = 2.0
MIN_MOMENTUM     = 0.5
MIN_RSI          = 45
MAX_RSI          = 65
AI_MIN_SCORE     = 60
MIN_QUOTE_VOL    = 5_000_000  # Min $5M hacim
MAX_PRICE        = 50         # $50 üstü = hisse tokenı, atla

# Kara liste
BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","MU","NVDA","TSLA","AAPL",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","MICHI",
}

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)

def tg(msg):
    try: bot.send_message(CHAT_ID, msg[:4096])
    except Exception as e: print(f"[TG] {e}")

# ─── SUPABASE ───
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        print("[SUPA] Bağlantı OK")
    except Exception as e:
        print(f"[SUPA] {e}")

def save_trade(data: dict):
    if not supa: return
    try: supa.table("trades").insert(data).execute()
    except Exception as e: print(f"[SAVE] {e}")

def load_trades_for_ai(symbol: str) -> pd.DataFrame:
    if not supa: return pd.DataFrame()
    try:
        r = supa.table("trades").select("*").eq("symbol", symbol).execute()
        rows = []
        for rec in r.data or []:
            try:
                pnl = float(rec.get("pnl") or 0)
                rows.append({
                    "momentum":     float(rec.get("momentum") or 0),
                    "volume_ratio": float(rec.get("volume_ratio") or 0),
                    "rsi":          float(rec.get("rsi") or 50),
                    "win":          1 if pnl > 0 else 0,
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
LAST_API = 0

def safe_api(func, *args, **kwargs):
    global LAST_API
    for attempt in range(4):
        try:
            wait = 0.4 - (time.time() - LAST_API)
            if wait > 0: time.sleep(wait)
            LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(5)
        except Exception as e:
            print(f"[API {attempt}] {e}")
            time.sleep(2)
    return None

# ─── GLOBAL STATE ───
positions    = {}   # açık pozisyonlar
pos_lock     = threading.Lock()
pending      = {}   # onay bekleyen sinyaller {symbol: {signal, ind, ilk_fiyat, zaman}}
pending_lock = threading.Lock()

# ─── COINGLASS ───
def get_coinglass(symbol: str) -> dict:
    """Funding rate, long/short oranı, open interest çek"""
    result = {"funding": None, "long_pct": None, "short_pct": None, "oi_change": None}
    if not COINGLASS_KEY:
        return result
    try:
        sym = symbol.split("/")[0]
        # Funding rate
        r = req.get(
            f"https://open-api-v3.coinglass.com/api/futures/fundingRate/current",
            headers={"CG-API-KEY": COINGLASS_KEY},
            params={"symbol": sym},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                bitget_data = next((x for x in data if "bitget" in x.get("exchangeName","").lower()), data[0])
                result["funding"] = float(bitget_data.get("fundingRate", 0) or 0)
    except Exception as e:
        print(f"[CG] {e}")

    try:
        sym = symbol.split("/")[0]
        # Long/Short oranı
        r = req.get(
            f"https://open-api-v3.coinglass.com/api/futures/globalLongShortAccountRatio/history",
            headers={"CG-API-KEY": COINGLASS_KEY},
            params={"symbol": sym, "interval": "5m", "limit": 1},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                result["long_pct"]  = float(data[-1].get("longAccount", 50))
                result["short_pct"] = float(data[-1].get("shortAccount", 50))
    except Exception as e:
        print(f"[CG-LS] {e}")

    return result

# ─── GÖSTERGELER ───
def calc_rsi(closes: pd.Series, period=14) -> float:
    delta = closes.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    return float((100 - (100 / (1 + gain / loss.replace(0, 0.0001)))).iloc[-1])

def calc_indicators(symbol: str):
    try:
        ohlcv = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=100)
        if not ohlcv or len(ohlcv) < 50: return None
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        ohlcv5 = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=30)
        if not ohlcv5: return None
        df5 = pd.DataFrame(ohlcv5, columns=["t","o","h","l","c","v"])

        ohlcv1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=50)
        if not ohlcv1h: return None
        df1h = pd.DataFrame(ohlcv1h, columns=["t","o","h","l","c","v"])

        c = df["c"]; v = df["v"]
        c5 = df5["c"]; c1h = df1h["c"]

        price    = float(c.iloc[-1])
        ema9     = float(c.ewm(span=9).mean().iloc[-1])
        ema20    = float(c.ewm(span=20).mean().iloc[-1])
        ema9_5   = float(c5.ewm(span=9).mean().iloc[-1])
        ema20_5  = float(c5.ewm(span=20).mean().iloc[-1])

        ema20_1h = float(c1h.ewm(span=20).mean().iloc[-1])
        ema50_1h = float(c1h.ewm(span=50).mean().iloc[-1])
        p1h      = float(c1h.iloc[-1])
        if p1h > ema20_1h and ema20_1h > ema50_1h: trend_1h = "UP"
        elif p1h < ema20_1h and ema20_1h < ema50_1h: trend_1h = "DOWN"
        else: trend_1h = "NEUTRAL"

        rsi      = calc_rsi(c)
        vol_avg  = float(v.rolling(20).mean().iloc[-1])
        if vol_avg <= 0: return None
        vol_ratio  = float(v.iloc[-1]) / vol_avg
        move_1     = (price - float(c.iloc[-2])) / float(c.iloc[-2]) * 100
        move_3     = (price - float(c.iloc[-4])) / float(c.iloc[-4]) * 100
        momentum   = abs(move_3)
        volatility = (float(df["h"].iloc[-1]) - float(df["l"].iloc[-1])) / price * 100
        avg5       = float(c.tail(5).mean())
        high5      = float(c.tail(5).max())
        low5       = float(c.tail(5).min())

        return {
            "symbol": symbol, "price": price,
            "ema9": ema9, "ema20": ema20,
            "ema9_5": ema9_5, "ema20_5": ema20_5,
            "trend_1h": trend_1h, "rsi": rsi,
            "vol_ratio": vol_ratio, "move_1": move_1,
            "move_3": move_3, "momentum": momentum,
            "volatility": volatility, "avg5": avg5,
            "high5": high5, "low5": low5,
        }
    except Exception as e:
        print(f"[IND {symbol}] {e}")
        return None

# ─── SİNYAL ───
def get_signal(ind: dict):
    p = ind["price"]; e9 = ind["ema9"]; e20 = ind["ema20"]
    e9_5 = ind["ema9_5"]; e20_5 = ind["ema20_5"]
    t1h = ind["trend_1h"]; rsi = ind["rsi"]
    vr = ind["vol_ratio"]; m1 = ind["move_1"]
    mom = ind["momentum"]; avg5 = ind["avg5"]
    high5 = ind["high5"]; low5 = ind["low5"]

    if vr  < MIN_VOLUME_RATIO: return None
    if mom < MIN_MOMENTUM:     return None
    if rsi < MIN_RSI:          return None
    if rsi > MAX_RSI:          return None
    if p >= high5 * 0.998:     return None  # Tepede LONG açma
    if p <= low5  * 1.002:     return None  # Dipte SHORT açma

    if (p > e20 and e9 > e20 and e9_5 > e20_5
            and m1 > 0 and p >= avg5 and t1h != "DOWN"):
        return "LONG"

    if (p < e20 and e9 < e20 and e9_5 < e20_5
            and m1 < -0.2 and p <= avg5
            and vr >= 2.5 and t1h == "DOWN"):
        return "SHORT"

    return None

# ─── AI SKOR ───
def ai_score(symbol: str, ind: dict) -> int:
    try:
        df = load_trades_for_ai(symbol)
        if df is None or len(df) < 20: return 65
        mask = (
            (df["volume_ratio"] >= ind["vol_ratio"] * 0.7) &
            (df["volume_ratio"] <= ind["vol_ratio"] * 1.3) &
            (df["momentum"]     >= ind["momentum"]  * 0.5)
        )
        similar = df[mask]
        if len(similar) < 5: return 65
        win_rate = similar["win"].mean() * 100
        bonus = 0
        if ind["vol_ratio"] >= 3.0: bonus += 10
        if ind["momentum"]  >= 1.5: bonus += 5
        if ind["rsi"] >= 55:        bonus += 5
        return min(95, int(win_rate + bonus))
    except: return 65

# ─── GPT ANALİZ ───
def gpt_analiz(symbol: str, signal: str, ind: dict, cg: dict, mod: str = "giris") -> tuple:
    """
    mod = "giris"  → GİR / PAS karar
    mod = "takip"  → DEVAM / KAPAT karar
    """
    if not OPENAI_KEY:
        return True, "GPT yok"
    try:
        sym = symbol.split("/")[0]

        # CoinGlass verileri
        funding_str = f"{cg['funding']*100:.4f}%" if cg.get("funding") is not None else "bilinmiyor"
        ls_str = f"Long %{cg['long_pct']:.1f} / Short %{cg['short_pct']:.1f}" if cg.get("long_pct") else "bilinmiyor"

        if mod == "giris":
            prompt = f"""Kripto futures trading uzmanısın. Bu işleme girmeliyim mi?

Coin: {sym}/USDT
Sinyal: {signal}
1h Trend: {ind['trend_1h']}
RSI: {ind['rsi']:.1f}
Hacim Artışı: {ind['vol_ratio']:.1f}x
Momentum (3 bar): {ind['move_3']:+.2f}%
Son bar: {ind['move_1']:+.2f}%

--- Piyasa Verileri ---
Funding Rate: {funding_str}
Long/Short Oranı: {ls_str}

Bu sinyale güvenilir mi? Sahte pump olabilir mi?
Sadece şu formatta cevap ver:
GİR — [1 cümle gerekçe]
veya
PAS — [1 cümle gerekçe]"""

        else:  # takip
            pnl_pct = ind.get("pnl_pct", 0)
            prompt = f"""Açık pozisyonu takip ediyorum. Devam etmeli miyim?

Coin: {sym}/USDT — {signal}
Anlık PnL: {pnl_pct:+.2f}%
RSI: {ind['rsi']:.1f}
Momentum: {ind['move_3']:+.2f}%
Funding Rate: {funding_str}
Long/Short: {ls_str}

Sadece şu formatta cevap ver:
DEVAM — [1 cümle gerekçe]
veya
KAPAT — [1 cümle gerekçe]"""

        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "max_tokens": 80,
                  "temperature": 0.2,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=10)

        if r.status_code == 200:
            yanit = r.json()["choices"][0]["message"]["content"].strip()
            if mod == "giris":
                gir = yanit.upper().startswith("GİR") or yanit.upper().startswith("GIR")
                return gir, yanit
            else:
                devam = yanit.upper().startswith("DEVAM")
                return devam, yanit
    except Exception as e:
        print(f"[GPT] {e}")

    return True, "GPT hatası"

# ─── TARAMA ───
def scan_active_coins() -> list:
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return []
        active = []
        for symbol, ticker in tickers.items():
            if not symbol.endswith("/USDT:USDT"): continue
            if ticker.get("quoteVolume", 0) < MIN_QUOTE_VOL: continue
            sym_name = symbol.split("/")[0]
            if sym_name in BLACKLIST: continue
            price = ticker.get("last", 0) or 0
            if price > MAX_PRICE: continue
            pct = abs(ticker.get("percentage", 0) or 0)
            if pct < 0.3: continue
            active.append({
                "symbol": symbol,
                "price":  price,
                "volume": ticker.get("quoteVolume", 0),
                "change": ticker.get("percentage", 0),
            })
        active.sort(key=lambda x: x["volume"], reverse=True)
        print(f"[SCAN] {len(active)} coin aktif")
        return active[:60]
    except Exception as e:
        print(f"[SCAN] {e}")
        return []

# ─── POZİSYON AÇ ───
def open_position(symbol: str, signal: str, ind: dict, score: int, gpt_yorum: str):
    with pos_lock:
        if symbol in positions: return
        if len(positions) >= MAX_OPEN: return
    try:
        safe_api(exchange.set_leverage, LEVERAGE, symbol)
        ticker = safe_api(exchange.fetch_ticker, symbol)
        if not ticker: return
        price  = ticker["last"]
        amount = float(exchange.amount_to_precision(
            symbol, (MARGIN * LEVERAGE) / price))
        side  = "buy" if signal == "LONG" else "sell"
        order = safe_api(exchange.create_market_order, symbol, side, amount)
        if not order: return
        entry = float(order.get("average") or price)
        if signal == "LONG":
            tp = round(entry * (1 + TP_PCT), 8)
            sl = round(entry * (1 - SL_PCT), 8)
        else:
            tp = round(entry * (1 - TP_PCT), 8)
            sl = round(entry * (1 + SL_PCT), 8)
        with pos_lock:
            positions[symbol] = {
                "signal": signal, "entry": entry,
                "tp": tp, "sl": sl, "max_pnl": 0.0,
                "score": score, "open_time": time.time(),
                "ind": ind, "last_gpt": time.time(),
            }
        sym = symbol.split("/")[0]
        tg(
            f"🚀 {sym} AÇILDI\n"
            f"Yön: {signal}\n"
            f"Giriş: {entry:.6f}\n"
            f"TP: {tp:.6f} (+%{TP_PCT*100:.0f})\n"
            f"SL: {sl:.6f} (-%{SL_PCT*100:.0f})\n"
            f"1h Trend: {ind['trend_1h']}\n"
            f"Hacim: {ind['vol_ratio']:.1f}x  RSI: {ind['rsi']:.0f}\n"
            f"🤖 GPT: {gpt_yorum}"
        )
    except Exception as e:
        print(f"[OPEN {symbol}] {e}")

# ─── POZİSYON KAPAT ───
def close_position(symbol: str, reason: str):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return
    try:
        ps   = safe_api(exchange.fetch_positions, [symbol])
        size = 0
        if ps:
            for p in ps:
                sz = abs(float(p.get("contracts") or p.get("size") or 0))
                if sz > 0: size = sz; break
        if size > 0:
            side = "sell" if pos["signal"] == "LONG" else "buy"
            safe_api(exchange.create_market_order, symbol, side, size,
                     params={"reduceOnly": True})
        ticker = safe_api(exchange.fetch_ticker, symbol)
        pnl = 0.0
        if ticker:
            cp = ticker["last"]
            if pos["signal"] == "LONG":
                pnl = (cp - pos["entry"]) / pos["entry"] * MARGIN * LEVERAGE
            else:
                pnl = (pos["entry"] - cp) / pos["entry"] * MARGIN * LEVERAGE
        ind = pos.get("ind", {})
        save_trade({
            "symbol": symbol, "signal": pos["signal"],
            "pnl": round(pnl, 4), "ai_score": pos["score"],
            "momentum": ind.get("momentum", 0),
            "volume_ratio": ind.get("vol_ratio", 0),
            "volatility": ind.get("volatility", 0),
            "rsi": ind.get("rsi", 0),
            "move_1": ind.get("move_1", 0),
            "move_3": ind.get("move_3", 0),
        })
        sym  = symbol.split("/")[0]
        icon = "🟢" if pnl >= 0 else "🔴"
        tg(f"{icon} {sym} KAPANDI\nSebep: {reason}\nPnL: {pnl:+.2f} USDT")
    except Exception as e:
        print(f"[CLOSE {symbol}] {e}")

# ─── YÖNETİCİ (TP/SL + GPT TAKİP) ───
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

                ticker = safe_api(exchange.fetch_ticker, symbol)
                if not ticker: continue
                price  = ticker["last"]
                entry  = pos["entry"]
                signal = pos["signal"]

                if signal == "LONG":
                    pnl_pct = (price - entry) / entry * 100
                else:
                    pnl_pct = (entry - price) / entry * 100
                pnl = pnl_pct / 100 * MARGIN * LEVERAGE

                if pnl > pos["max_pnl"]:
                    pos["max_pnl"] = pnl
                max_pnl = pos["max_pnl"]

                # SL
                if pnl_pct <= -SL_PCT * 100:
                    close_position(symbol, f"STOP LOSS -%{SL_PCT*100:.0f}")
                    continue

                # Breakeven
                if max_pnl >= MARGIN * 0.10 and pnl <= MARGIN * 0.01:
                    close_position(symbol, f"BREAKEVEN +{pnl:.2f}")
                    continue

                # Trailing
                if max_pnl >= MARGIN * 0.20:
                    trail_floor = max_pnl - MARGIN * 0.10
                    if pnl <= trail_floor:
                        close_position(symbol, f"TRAILING +{pnl:.2f} 🚀")
                        continue

                # TP
                if pnl_pct >= TP_PCT * 100:
                    close_position(symbol, f"TAKE PROFIT +%{TP_PCT*100:.0f} 🎯")
                    continue

                # Zaman aşımı
                if time.time() - pos["open_time"] > 45 * 60:
                    close_position(symbol, "ZAMAN AŞIMI")
                    continue

                # GPT canlı takip — her 5 dakikada bir
                if time.time() - pos.get("last_gpt", 0) > 300:
                    try:
                        ind = pos.get("ind", {})
                        ind["pnl_pct"] = pnl_pct
                        cg = get_coinglass(symbol)
                        devam, yorum = gpt_analiz(symbol, signal, ind, cg, mod="takip")
                        pos["last_gpt"] = time.time()
                        print(f"[GPT-TAKİP] {symbol.split('/')[0]} → {'DEVAM' if devam else 'KAPAT'} | {yorum}")
                        if not devam:
                            close_position(symbol, f"GPT KAPAT: {yorum[:50]}")
                            continue
                    except Exception as e:
                        print(f"[GPT-TAKİP] {e}")

        except Exception as e:
            print(f"[MANAGE] {e}")

# ─── ONAY DÖNGÜSÜ (3 dakika bekle) ───
def confirm_loop():
    """Sinyali 3 dakika izle, sahte pump ise iptal et"""
    while True:
        time.sleep(10)
        try:
            now = time.time()
            with pending_lock:
                syms = list(pending.keys())

            for symbol in syms:
                with pending_lock:
                    p = pending.get(symbol)
                if not p: continue

                elapsed = now - p["zaman"]

                # 3 dakika dolmadı — izlemeye devam
                if elapsed < CONFIRM_WAIT:
                    # Fiyat hala aynı yönde mi?
                    ticker = safe_api(exchange.fetch_ticker, symbol)
                    if ticker:
                        cur_price = ticker["last"]
                        ilk_fiyat = p["ilk_fiyat"]
                        signal    = p["signal"]
                        # Sinyal yönünün tersi olduysa iptal
                        if signal == "LONG" and cur_price < ilk_fiyat * 0.99:
                            print(f"[CONFIRM] {symbol.split('/')[0]} sahte pump — iptal")
                            tg(f"⚠️ {symbol.split('/')[0]} sahte pump tespit edildi, işlem açılmadı")
                            with pending_lock:
                                pending.pop(symbol, None)
                        elif signal == "SHORT" and cur_price > ilk_fiyat * 1.01:
                            print(f"[CONFIRM] {symbol.split('/')[0]} sahte dump — iptal")
                            with pending_lock:
                                pending.pop(symbol, None)
                    continue

                # 3 dakika doldu — GPT son onay
                with pending_lock:
                    pending.pop(symbol, None)

                with pos_lock:
                    if symbol in positions: continue
                    if len(positions) >= MAX_OPEN: continue

                ind   = p["ind"]
                score = p["score"]
                signal= p["signal"]

                # Güncel göstergeleri al
                ind_yeni = calc_indicators(symbol)
                if ind_yeni:
                    ind = ind_yeni

                # Sinyal hala geçerli mi?
                sig_yeni = get_signal(ind)
                if sig_yeni != signal:
                    print(f"[CONFIRM] {symbol.split('/')[0]} sinyal değişti — iptal")
                    continue

                # CoinGlass + GPT son karar
                cg = get_coinglass(symbol)
                gir, yorum = gpt_analiz(symbol, signal, ind, cg, mod="giris")
                sym = symbol.split("/")[0]
                print(f"[CONFIRM-GPT] {sym} → {'GİR ✅' if gir else 'PAS ❌'} | {yorum}")

                if gir:
                    open_position(symbol, signal, ind, score, yorum)
                else:
                    tg(f"⛔ {sym} GPT reddetti: {yorum}")

        except Exception as e:
            print(f"[CONFIRM] {e}")

# ─── TARAYICI ───
def scanner_loop():
    while True:
        try:
            with pos_lock:
                open_count = len(positions)
                open_syms  = set(positions.keys())
            with pending_lock:
                pending_syms = set(pending.keys())

            if open_count >= MAX_OPEN:
                time.sleep(10)
                continue

            active = scan_active_coins()
            if not active:
                time.sleep(SCAN_INTERVAL)
                continue

            for coin in active:
                symbol = coin["symbol"]
                if symbol in open_syms: continue
                if symbol in pending_syms: continue
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break

                ind = calc_indicators(symbol)
                if not ind: continue
                signal = get_signal(ind)
                if not signal: continue
                score = ai_score(symbol, ind)
                if score < AI_MIN_SCORE:
                    continue

                sym = symbol.split("/")[0]
                print(f"[SİNYAL] {sym} {signal} RSI={ind['rsi']:.0f} vol={ind['vol_ratio']:.1f}x trend={ind['trend_1h']} — 3dk onay bekleniyor")

                # Bekleme listesine al
                with pending_lock:
                    pending[symbol] = {
                        "signal":    signal,
                        "ind":       ind,
                        "score":     score,
                        "ilk_fiyat": ind["price"],
                        "zaman":     time.time(),
                    }
                tg(f"🔍 {sym} {signal} sinyali — 3 dakika izleniyor...\nRSI:{ind['rsi']:.0f} Hacim:{ind['vol_ratio']:.1f}x Trend:{ind['trend_1h']}")
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

# ─── TELEGRAM KOMUTLAR ───
@bot.message_handler(commands=["durum","status"])
def cmd_durum(msg):
    with pos_lock:
        if not positions:
            bot.send_message(msg.chat.id, "📊 Açık pozisyon yok.")
            return
        lines = ["📊 AÇIK POZİSYONLAR\n"]
        for sym, pos in positions.items():
            ticker = safe_api(exchange.fetch_ticker, sym)
            if ticker:
                price = ticker["last"]
                pnl = (price-pos["entry"])/pos["entry"]*MARGIN*LEVERAGE if pos["signal"]=="LONG" else (pos["entry"]-price)/pos["entry"]*MARGIN*LEVERAGE
                icon = "🟢" if pnl >= 0 else "🔴"
                lines.append(f"{icon} {sym.split('/')[0]} {pos['signal']}\nGiriş:{pos['entry']:.6f} → {price:.6f}\nPnL:{pnl:+.2f} USDT\n")
        bot.send_message(msg.chat.id, "\n".join(lines))

@bot.message_handler(commands=["bekleyen"])
def cmd_bekleyen(msg):
    with pending_lock:
        if not pending:
            bot.send_message(msg.chat.id, "⏳ Bekleyen sinyal yok.")
            return
        lines = ["⏳ BEKLEYEN SİNYALLER\n"]
        for sym, p in pending.items():
            kalan = max(0, CONFIRM_WAIT - (time.time() - p["zaman"]))
            lines.append(f"{sym.split('/')[0]} {p['signal']} — {kalan:.0f}sn kaldı")
        bot.send_message(msg.chat.id, "\n".join(lines))

@bot.message_handler(commands=["kapat"])
def cmd_kapat(msg):
    text = msg.text.replace("/kapat","").strip().upper()
    if not text:
        bot.send_message(msg.chat.id, "Kullanım: /kapat SOL"); return
    symbol = f"{text}/USDT:USDT"
    with pos_lock:
        if symbol not in positions:
            bot.send_message(msg.chat.id, f"❌ {text} açık pozisyon yok."); return
    close_position(symbol, "MANUEL KAPANIŞ")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock:
        syms = list(positions.keys())
    for s in syms:
        close_position(s, "MANUEL - HEPSI KAPAT")

# ─── MAIN ───
if __name__ == "__main__":
    print("🚀 SADIK DYNAMIC SCANNER BOT v3 BAŞLIYOR...")
    threading.Thread(target=health_server,  daemon=True).start()
    threading.Thread(target=manage_loop,    daemon=True).start()
    threading.Thread(target=scanner_loop,   daemon=True).start()
    threading.Thread(target=confirm_loop,   daemon=True).start()
    print("[HEALTH] | [MANAGE] | [SCANNER] | [CONFIRM] — Tümü başladı")
    tg(
        "🚀 SADIK DYNAMIC SCANNER BOT v3\n\n"
        f"Kaldıraç: {LEVERAGE}x\n"
        f"Marjin: {MARGIN} USDT/işlem\n"
        f"TP: +%{TP_PCT*100:.0f} | SL: -%{SL_PCT*100:.0f}\n"
        f"Max pozisyon: {MAX_OPEN}\n\n"
        "✅ Yeni özellikler:\n"
        "• 3 dakika onay — sahte pump engeli\n"
        "• CoinGlass funding + long/short analizi\n"
        "• GPT canlı takip (5dk'da bir)\n"
        "• Tepede LONG engeli (RSI + tepe filtresi)\n"
        "• Hisse tokenları engeli ($50+)\n\n"
        "Komutlar:\n"
        "/durum — açık pozisyonlar\n"
        "/bekleyen — onay bekleyenler\n"
        "/kapat SOL — manuel kapat\n"
        "/hepsikapat — hepsini kapat"
    )
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"[POLLING] {e}")
            time.sleep(5)
