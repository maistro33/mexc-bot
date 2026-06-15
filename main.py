#!/usr/bin/env python3
"""
SADIK DYNAMIC SCANNER BOT
Tüm Bitget coinlerini tarar, pump yakalayan, AI destekli
"""

import os, time, json, threading
import ccxt
import pandas as pd
import numpy as np
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

# Risk ayarları
LEVERAGE     = 5       # 5x - güvenli
MARGIN       = 10.0    # Her işlem 10 USDT
TP1_PCT      = 0.02    # %2 → %50 kapat, SL breakeven
TP2_PCT      = 0.03    # %3 → %25 kapat
TP3_PCT      = 0.05    # %5 → kalanı kapat
SL_PCT       = 0.02    # %2 stop loss
MAX_OPEN     = 3       # Max açık pozisyon
SCAN_INTERVAL= 30      # Saniye

# Filtreler
MIN_VOLUME_RATIO = 2.0   # Normal hacmin 2x+ artması
MIN_MOMENTUM     = 0.8   # %0.8 fiyat hareketi
MIN_RSI          = 45    # RSI minimum
MAX_RSI          = 75    # RSI maximum (aşırı alım değil)
AI_MIN_SCORE     = 60    # AI minimum skor

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)

def tg(msg):
    try:
        bot.send_message(CHAT_ID, msg)
    except Exception as e:
        print(f"[TG] {e}")

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
    try:
        supa.table("trades").insert(data).execute()
    except Exception as e:
        print(f"[SAVE] {e}")

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
                    "volatility":   float(rec.get("volatility") or 0),
                    "rsi":          float(rec.get("rsi") or 50),
                    "move_1":       float(rec.get("move_1") or 0),
                    "move_3":       float(rec.get("move_3") or 0),
                    "win":          1 if pnl > 0 else 0,
                })
            except: pass
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"[AI LOAD] {e}")
        return pd.DataFrame()

# ─── EXCHANGE ───
exchange = ccxt.bitget({
    "apiKey":   BITGET_API,
    "secret":   BITGET_SEC,
    "password": BITGET_PASS,
    "enableRateLimit": True,
    "options":  {"defaultType": "swap"},
})

LAST_API = 0

def safe_api(func, *args, **kwargs):
    global LAST_API
    for attempt in range(4):
        try:
            wait = 0.4 - (time.time() - LAST_API)
            if wait > 0:
                time.sleep(wait)
            LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(5)
        except Exception as e:
            print(f"[API {attempt}] {e}")
            time.sleep(2)
    return None

# ─── GLOBAL STATE ───
positions  = {}   # symbol → pozisyon dict
pos_lock   = threading.Lock()
ai_models  = {}   # symbol → model (lazy load)

# ─── GÖSTERGELERs ───
def calc_rsi(closes: pd.Series, period=14) -> float:
    delta = closes.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.0001)
    rsi   = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def calc_indicators(symbol: str):
    """OHLCV çek, göstergeleri hesapla"""
    try:
        # 1m bar
        ohlcv = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=100)
        if not ohlcv or len(ohlcv) < 50:
            return None
        df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

        # 5m trend
        ohlcv5 = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=30)
        if not ohlcv5:
            return None
        df5 = pd.DataFrame(ohlcv5, columns=["t","o","h","l","c","v"])

        # 1h büyük trend — LONG/SHORT filtresi için
        ohlcv1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=50)
        if not ohlcv1h:
            return None
        df1h = pd.DataFrame(ohlcv1h, columns=["t","o","h","l","c","v"])

        c   = df["c"]
        v   = df["v"]
        c5  = df5["c"]
        c1h = df1h["c"]

        price    = float(c.iloc[-1])
        ema9     = float(c.ewm(span=9).mean().iloc[-1])
        ema20    = float(c.ewm(span=20).mean().iloc[-1])
        ema9_5   = float(c5.ewm(span=9).mean().iloc[-1])
        ema20_5  = float(c5.ewm(span=20).mean().iloc[-1])

        # 1h büyük trend — bu filtre JCT gibi düşüş trendinde LONG açılmasını engeller
        ema20_1h = float(c1h.ewm(span=20).mean().iloc[-1])
        ema50_1h = float(c1h.ewm(span=50).mean().iloc[-1])
        price_1h = float(c1h.iloc[-1])
        # 1h trend yönü: yukarı mı aşağı mı?
        trend_1h = "UP" if (price_1h > ema20_1h and ema20_1h > ema50_1h) else \
                   "DOWN" if (price_1h < ema20_1h and ema20_1h < ema50_1h) else "NEUTRAL"

        rsi      = calc_rsi(c)

        vol_avg  = float(v.rolling(20).mean().iloc[-1])
        if vol_avg <= 0:
            return None
        vol_ratio = float(v.iloc[-1]) / vol_avg

        move_1   = (price - float(c.iloc[-2])) / float(c.iloc[-2]) * 100
        move_3   = (price - float(c.iloc[-4])) / float(c.iloc[-4]) * 100
        momentum = abs(move_3)
        volatility = (float(df["h"].iloc[-1]) - float(df["l"].iloc[-1])) / price * 100

        # Sahte breakout filtresi
        avg5 = float(c.tail(5).mean())

        return {
            "symbol":     symbol,
            "price":      price,
            "ema9":       ema9,
            "ema20":      ema20,
            "ema9_5":     ema9_5,
            "ema20_5":    ema20_5,
            "trend_1h":   trend_1h,   # 1h büyük trend
            "rsi":        rsi,
            "vol_ratio":  vol_ratio,
            "move_1":     move_1,
            "move_3":     move_3,
            "momentum":   momentum,
            "volatility": volatility,
            "avg5":       avg5,
        }
    except Exception as e:
        print(f"[IND {symbol}] {e}")
        return None

# ─── SİNYAL ───
def get_signal(ind: dict) -> str | None:
    """LONG veya SHORT sinyali döndür, yoksa None"""
    p      = ind["price"]
    e9     = ind["ema9"]
    e20    = ind["ema20"]
    e9_5   = ind["ema9_5"]
    e20_5  = ind["ema20_5"]
    t1h    = ind["trend_1h"]   # 1h büyük trend
    rsi    = ind["rsi"]
    vr     = ind["vol_ratio"]
    m1     = ind["move_1"]
    mom    = ind["momentum"]
    avg5   = ind["avg5"]

    # Temel filtreler
    if vr    < MIN_VOLUME_RATIO: return None
    if mom   < MIN_MOMENTUM:     return None
    if rsi   < MIN_RSI:          return None
    if rsi   > MAX_RSI:          return None

    # LONG — sadece 1h trend UP veya NEUTRAL ise
    if (p > e20 and e9 > e20           # 1m trend yukarı
        and e9_5 > e20_5               # 5m trend yukarı
        and m1 > 0                     # son bar yeşil
        and p >= avg5                  # sahte breakout değil
        and t1h != "DOWN"):            # 1h düşüş trendinde LONG açma!
        return "LONG"

    # SHORT — sadece 1h trend DOWN veya NEUTRAL ise
    if (p < e20 and e9 < e20           # 1m trend aşağı
        and e9_5 < e20_5               # 5m trend aşağı
        and m1 < 0                     # son bar kırmızı
        and p <= avg5                  # sahte breakout değil
        and t1h != "UP"):              # 1h yükseliş trendinde SHORT açma!
        return "SHORT"

    return None

# ─── AI SKOR ───
def ai_score(symbol: str, ind: dict) -> int:
    """Geçmiş veriye göre basit skor hesapla"""
    try:
        df = load_trades_for_ai(symbol)
        if df is None or len(df) < 20:
            return 65  # Varsayılan - nötr

        # Benzer koşullarda kaç kez kazandık?
        mask = (
            (df["volume_ratio"] >= ind["vol_ratio"] * 0.7) &
            (df["volume_ratio"] <= ind["vol_ratio"] * 1.3) &
            (df["momentum"]     >= ind["momentum"]  * 0.5)
        )
        similar = df[mask]
        if len(similar) < 5:
            return 65

        win_rate = similar["win"].mean() * 100
        # Hacim ve momentum bonusu
        bonus = 0
        if ind["vol_ratio"] >= 3.0: bonus += 10
        if ind["momentum"]  >= 1.5: bonus += 5
        if ind["rsi"] >= 55:        bonus += 5

        return min(95, int(win_rate + bonus))
    except Exception as e:
        print(f"[AI] {e}")
        return 65

# ─── AKTİF KOİN TARAMASI ───
def scan_active_coins() -> list:
    """Hacmi patlayan coinleri bul"""
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers:
            return []

        active = []
        for symbol, ticker in tickers.items():
            # Sadece USDT perpetual
            if not symbol.endswith("/USDT:USDT"):
                continue
            # Temel veri kontrolü
            if not ticker.get("quoteVolume"):
                continue
            # Çok küçük coinleri atla
            if ticker.get("quoteVolume", 0) < 100000:
                continue
            # Fiyat hareketi var mı?
            pct = abs(ticker.get("percentage", 0) or 0)
            if pct < 0.5:
                continue

            active.append({
                "symbol":  symbol,
                "price":   ticker.get("last", 0),
                "volume":  ticker.get("quoteVolume", 0),
                "change":  ticker.get("percentage", 0),
            })

        # Hacme göre sırala, top 50
        active.sort(key=lambda x: x["volume"], reverse=True)
        return active[:50]
    except Exception as e:
        print(f"[SCAN] {e}")
        return []

# ─── POZİSYON AÇ ───
def open_position(symbol: str, signal: str, ind: dict, score: int):
    with pos_lock:
        if symbol in positions:
            return
        if len(positions) >= MAX_OPEN:
            return

    try:
        # Kaldıraç ayarla
        safe_api(exchange.set_leverage, LEVERAGE, symbol)

        # Fiyat al
        ticker = safe_api(exchange.fetch_ticker, symbol)
        if not ticker:
            return
        price  = ticker["last"]

        # Miktar hesapla
        amount = float(exchange.amount_to_precision(
            symbol, (MARGIN * LEVERAGE) / price
        ))

        side = "buy" if signal == "LONG" else "sell"
        order = safe_api(exchange.create_market_order, symbol, side, amount)
        if not order:
            return

        entry = float(order.get("average") or price)

        # SL hesapla
        if signal == "LONG":
            sl = round(entry * (1 - SL_PCT), 8)
        else:
            sl = round(entry * (1 + SL_PCT), 8)

        pos = {
            "symbol":    symbol,
            "signal":    signal,
            "entry":     entry,
            "sl":        sl,
            "amount":    MARGIN,
            "contracts": amount,
            "tp1_done":  False,
            "tp2_done":  False,
            "max_pnl":   0.0,
            "score":     score,
            "open_time": time.time(),
            "ind":       ind,
        }

        with pos_lock:
            positions[symbol] = pos

        sym = symbol.split("/")[0]
        tg(
            f"🚀 {sym} AÇILDI\n"
            f"Yön: {signal}\n"
            f"Giriş: {entry:.6f}\n"
            f"TP1: +%{TP1_PCT*100:.0f} → %50 kapat\n"
            f"TP2: +%{TP2_PCT*100:.0f} → %25 kapat\n"
            f"TP3: +%{TP3_PCT*100:.0f} → tam kapat\n"
            f"SL: -%{SL_PCT*100:.0f}\n"
            f"AI Skor: %{score}\n"
            f"Hacim: {ind['vol_ratio']:.1f}x\n"
            f"RSI: {ind['rsi']:.0f}\n"
            f"1h Trend: {ind['trend_1h']}\n"
            f"Kaldıraç: {LEVERAGE}x"
        )
    except Exception as e:
        print(f"[OPEN {symbol}] {e}")

# ─── POZİSYON KAPAT ───
def close_position(symbol: str, reason: str):
    with pos_lock:
        pos = positions.get(symbol)
        if not pos:
            return
        del positions[symbol]

    try:
        # Gerçek pozisyon büyüklüğü
        ps = safe_api(exchange.fetch_positions, [symbol])
        size = 0
        if ps:
            for p in ps:
                sz = abs(float(p.get("contracts") or p.get("size") or 0))
                if sz > 0:
                    size = sz
                    break

        if size > 0:
            side = "sell" if pos["signal"] == "LONG" else "buy"
            safe_api(exchange.create_market_order, symbol, side, size,
                     params={"reduceOnly": True})

        # PnL hesapla
        ticker = safe_api(exchange.fetch_ticker, symbol)
        pnl = 0.0
        if ticker:
            cp = ticker["last"]
            if pos["signal"] == "LONG":
                pnl = (cp - pos["entry"]) / pos["entry"] * MARGIN * LEVERAGE
            else:
                pnl = (pos["entry"] - cp) / pos["entry"] * MARGIN * LEVERAGE

        # Supabase'e kaydet
        ind = pos.get("ind", {})
        save_trade({
            "symbol":       symbol,
            "signal":       pos["signal"],
            "pnl":          round(pnl, 4),
            "ai_score":     pos["score"],
            "momentum":     ind.get("momentum", 0),
            "volume_ratio": ind.get("vol_ratio", 0),
            "volatility":   ind.get("volatility", 0),
            "rsi":          ind.get("rsi", 0),
            "move_1":       ind.get("move_1", 0),
            "move_3":       ind.get("move_3", 0),
        })

        sym  = symbol.split("/")[0]
        icon = "🟢" if pnl >= 0 else "🔴"
        sign = "+" if pnl >= 0 else ""
        tg(
            f"{icon} {sym} KAPANDI\n"
            f"Sebep: {reason}\n"
            f"PnL: {sign}{pnl:.2f} USDT\n"
            f"Yön: {pos['signal']}"
        )
    except Exception as e:
        print(f"[CLOSE {symbol}] {e}")

# ─── POZİSYON YÖNETİCİ ───
def manage_loop():
    """Açık pozisyonları izle, kademeli TP/SL tetikle"""
    while True:
        time.sleep(5)
        try:
            with pos_lock:
                syms = list(positions.keys())

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos:
                    continue

                ticker = safe_api(exchange.fetch_ticker, symbol)
                if not ticker:
                    continue

                price  = ticker["last"]
                entry  = pos["entry"]
                signal = pos["signal"]

                if signal == "LONG":
                    pnl_pct = (price - entry) / entry
                else:
                    pnl_pct = (entry - price) / entry

                pnl = pnl_pct * MARGIN * LEVERAGE

                # Max PnL güncelle
                if pnl > pos["max_pnl"]:
                    pos["max_pnl"] = pnl

                max_pnl = pos["max_pnl"]
                sym     = symbol.split("/")[0]

                # ─── STOP LOSS ───
                if pnl_pct <= -SL_PCT:
                    close_position(symbol, f"STOP LOSS -%{SL_PCT*100:.0f}")
                    continue

                # ─── BREAKEVEN (TP1 sonrası SL breakeven'e çekildi) ───
                if pos["tp1_done"] and pnl <= 0:
                    close_position(symbol, "BREAKEVEN KORUMA")
                    continue

                # ─── TRAILING STOP ───
                if max_pnl >= MARGIN * 0.15 and pnl <= max_pnl - MARGIN * 0.10:
                    close_position(symbol, f"TRAILING +{pnl:.2f}")
                    continue

                # ─── TP1 +%2 → %50 kapat ───
                if not pos["tp1_done"] and pnl_pct >= TP1_PCT:
                    try:
                        # Yarısını kapat
                        ps = safe_api(exchange.fetch_positions, [symbol])
                        size = 0
                        if ps:
                            for p in ps:
                                sz = abs(float(p.get("contracts") or p.get("size") or 0))
                                if sz > 0:
                                    size = sz
                                    break
                        if size > 0:
                            half = float(exchange.amount_to_precision(symbol, size * 0.5))
                            side = "sell" if signal == "LONG" else "buy"
                            safe_api(exchange.create_market_order, symbol, side, half,
                                     params={"reduceOnly": True})
                        pos["tp1_done"] = True
                        partial_pnl = pnl_pct * MARGIN * LEVERAGE * 0.5
                        tg(f"🟡 {sym} TP1 +%{TP1_PCT*100:.0f}\n"
                           f"%50 kapatıldı • +{partial_pnl:.2f} USDT\n"
                           f"SL breakeven'e çekildi ✅")
                    except Exception as e:
                        print(f"[TP1 {symbol}] {e}")
                    continue

                # ─── TP2 +%3 → %25 kapat ───
                if pos["tp1_done"] and not pos["tp2_done"] and pnl_pct >= TP2_PCT:
                    try:
                        ps = safe_api(exchange.fetch_positions, [symbol])
                        size = 0
                        if ps:
                            for p in ps:
                                sz = abs(float(p.get("contracts") or p.get("size") or 0))
                                if sz > 0:
                                    size = sz
                                    break
                        if size > 0:
                            quarter = float(exchange.amount_to_precision(symbol, size * 0.5))
                            side = "sell" if signal == "LONG" else "buy"
                            safe_api(exchange.create_market_order, symbol, side, quarter,
                                     params={"reduceOnly": True})
                        pos["tp2_done"] = True
                        partial_pnl = pnl_pct * MARGIN * LEVERAGE * 0.25
                        tg(f"🟡 {sym} TP2 +%{TP2_PCT*100:.0f}\n"
                           f"%25 kapatıldı • +{partial_pnl:.2f} USDT")
                    except Exception as e:
                        print(f"[TP2 {symbol}] {e}")
                    continue

                # ─── TP3 +%5 → tam kapat ───
                if pos["tp2_done"] and pnl_pct >= TP3_PCT:
                    close_position(symbol, f"TP3 +%{TP3_PCT*100:.0f} 🎯")
                    continue

                # ─── ZAMAN AŞIMI (45 dakika) ───
                if time.time() - pos["open_time"] > 45 * 60:
                    close_position(symbol, "ZAMAN AŞIMI")
                    continue

        except Exception as e:
            print(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    """Tüm coinleri tara, sinyal bul"""
    while True:
        try:
            with pos_lock:
                open_count = len(positions)
                open_syms  = set(positions.keys())

            if open_count >= MAX_OPEN:
                time.sleep(10)
                continue

            # Aktif coinleri bul
            active = scan_active_coins()
            if not active:
                time.sleep(SCAN_INTERVAL)
                continue

            print(f"[SCAN] {len(active)} aktif coin taranıyor...")

            for coin in active:
                symbol = coin["symbol"]

                # Zaten açık mı?
                if symbol in open_syms:
                    continue

                # Max pozisyon kontrolü
                with pos_lock:
                    if len(positions) >= MAX_OPEN:
                        break

                # Göstergeleri hesapla
                ind = calc_indicators(symbol)
                if not ind:
                    continue

                # Sinyal var mı?
                signal = get_signal(ind)
                if not signal:
                    continue

                # AI skoru
                score = ai_score(symbol, ind)
                if score < AI_MIN_SCORE:
                    print(f"[SKIP] {symbol} AI skor düşük: %{score}")
                    continue

                sym = symbol.split("/")[0]
                print(f"[SIGNAL] {sym} {signal} skor=%{score} RSI={ind['rsi']:.0f} vol={ind['vol_ratio']:.1f}x")

                # İşlem aç
                open_position(symbol, signal, ind, score)

                # Bir sonraki coini taramadan önce kısa bekle
                time.sleep(2)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"[SCANNER] {e}")
            time.sleep(10)

# ─── HEALTH CHECK ───
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
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
                if pos["signal"] == "LONG":
                    pnl = (price - pos["entry"]) / pos["entry"] * MARGIN * LEVERAGE
                else:
                    pnl = (pos["entry"] - price) / pos["entry"] * MARGIN * LEVERAGE
                icon = "🟢" if pnl >= 0 else "🔴"
                lines.append(
                    f"{icon} {sym.split('/')[0]} {pos['signal']}\n"
                    f"Giriş: {pos['entry']:.4f} → {price:.4f}\n"
                    f"PnL: {pnl:+.2f} USDT\n"
                )
        bot.send_message(msg.chat.id, "\n".join(lines))

@bot.message_handler(commands=["kapat","close"])
def cmd_kapat(msg):
    text = msg.text.replace("/kapat","").replace("/close","").strip().upper()
    if not text:
        bot.send_message(msg.chat.id, "Kullanım: /kapat BTC")
        return
    symbol = f"{text}/USDT:USDT"
    with pos_lock:
        if symbol not in positions:
            bot.send_message(msg.chat.id, f"❌ {text} açık pozisyon yok.")
            return
    close_position(symbol, "MANUEL KAPANIŞ")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock:
        syms = list(positions.keys())
    for s in syms:
        close_position(s, "MANUEL - HEPSI KAPAT")

# ─── MAIN ───
if __name__ == "__main__":
    print("🚀 SADIK DYNAMIC SCANNER BOT BAŞLIYOR...")

    # Health server
    threading.Thread(target=health_server, daemon=True).start()
    print("[HEALTH] Port 8080 hazır")

    # Manager thread
    threading.Thread(target=manage_loop, daemon=True).start()
    print("[MANAGE] Pozisyon yöneticisi başladı")

    # Scanner thread
    threading.Thread(target=scanner_loop, daemon=True).start()
    print("[SCANNER] Tarayıcı başladı")

    tg(
        "🚀 SADIK DYNAMIC SCANNER BOT BAŞLADI\n\n"
        f"Kaldıraç: {LEVERAGE}x\n"
        f"Marjin: {MARGIN} USDT/işlem\n"
        f"TP1: +%{TP1_PCT*100:.0f} → %50 kapat\n"
        f"TP2: +%{TP2_PCT*100:.0f} → %25 kapat\n"
        f"TP3: +%{TP3_PCT*100:.0f} → tam kapat\n"
        f"SL: -%{SL_PCT*100:.0f}\n"
        f"Max pozisyon: {MAX_OPEN}\n"
        f"1h Trend filtresi: AKTİF ✅\n"
        "Tüm coinler taranıyor...\n\n"
        "Komutlar:\n"
        "/durum — açık pozisyonlar\n"
        "/kapat BTC — manuel kapat\n"
        "/hepsikapat — hepsini kapat"
    )

    # Telegram polling
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"[POLLING] {e}")
            time.sleep(5)
