#!/usr/bin/env python3
"""
SADIK SCALP FAST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strateji: Gir → Kâr Al → Çık (hızlı scalp), aynı sinyal kaynakları korunuyor:
  1. CoinSonar V2 — Telegram kanalı (Telethon)
  2. FuturesKripto — Telegram kanalı (Telethon)
  3. Manuel — Sen bota yazarsın
  4. Bağımsız tarayıcı — ani pump/dump tespiti

Pozisyon:
  Margin: 15$ | Kaldıraç: 5x | Pozisyon büyüklüğü: 75$

Çıkış mantığı (TEK TP + TEK SL + KÂR FLOORU İLE TRAILING):
  - SL: -%0.8 (net kayıp ≈ -$0.69, komisyonlar dahil)
  - Net kâr $0.80'e ulaşılınca pozisyon KAPANMAZ — trailing moduna geçer.
    Fiyat lehte gitmeye devam ettiği sürece pozisyon açık kalır.
    Fiyat geri dönüp net kârı tekrar $0.80 seviyesine indirirse,
    o anda LİMİT emirle kapatılıp $0.80 net kâr kasaya konur.
  - Trigger'a ulaşılmadan SL'e çarparsa normal SL ile kapanır.

Emir tipi:
  - GİRİŞ: sadece LİMİT emir (birkaç deneme, fiyat güncellenerek)
  - ÇIKIŞ: sadece LİMİT emir (SL/floor tetiklenince agresif fiyatlanan
    limit emirlerle hızlı doldurulur — market emir KULLANILMAZ)
"""

import os, time, threading, logging, re, asyncio
import ccxt
import pandas as pd
import telebot
from supabase import create_client
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SCALP_FAST")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN    = os.getenv("TELE_TOKEN", "")
CHAT_ID       = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API    = os.getenv("BITGET_API", "")
BITGET_SEC    = os.getenv("BITGET_SEC", "")
BITGET_PASS   = os.getenv("BITGET_PASS", "")
SUPA_URL      = os.getenv("SUPABASE_URL", "")
SUPA_KEY      = os.getenv("SUPABASE_KEY", "")
TG_API_ID     = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH   = os.getenv("TG_API_HASH", "")
TG_SESSION    = os.getenv("TG_SESSION", "")

COINSONAR_KANAL     = "CoinSonarV2"
FUTURESKRIPTO_KANAL = "FuturesKripto"

# ── Pozisyon ──
MARGIN          = 15.0
LEVERAGE        = 5
POS_SIZE        = MARGIN * LEVERAGE     # 75$
COMMISSION      = 0.0006                # taker, tek yön
ROUNDTRIP_FEE   = POS_SIZE * COMMISSION * 2   # ≈ 0.09$ (giriş+çıkış)

MAX_OPEN_AUTO   = 2
MAX_OPEN_MANUEL = 3
MAX_DAILY_LOSS  = -15.0
MAX_SURE        = 240    # dk — süre dolunca limitle kapat

# ── Çıkış parametreleri ──
SL_PCT        = 0.80     # sabit -%0.8 SL (tüm kaynaklarda aynı)
NET_TP_HEDEF  = 0.80     # $ — trigger + floor seviyesi (masraf sonrası net)

RECENTLY_TTL  = 1800     # coin kapandıktan sonra 30dk tekrar açılmasın

# ── Limit emir parametreleri (SADECE LİMİT — market emir yok) ──
GIRIS_DENEME       = 5     # limit giriş: kaç kez fiyat güncellenip denenir
GIRIS_BEKLE_SN     = 3     # her denemede bekleme süresi
GIRIS_OFFSET_PCT   = 0.05  # ilk giriş limiti mid'den ne kadar içeride denensin

KAPAT_DENEME       = 8     # limit kapatma: kaç kez agresifleştirilerek denenir
KAPAT_BEKLE_SN     = 2     # her denemede bekleme süresi
KAPAT_ADIM_PCT     = 0.06  # her başarısız denemede fiyat bu kadar daha agresifleşir
                            # (spread'i aşamalı geçip hızlı dolum sağlar, yine de LIMIT emir)

# ── 15m Filtre (CoinSonar için) ──
RSI_MIN = 30
RSI_MAX = 55
MIN_PRICE    = 0.0001
MAX_PRICE    = 100.0
MIN_TURNOVER = 200_000

# ── Bağımsız tarayıcı (pump/dump) ──
SCAN_INTERVAL     = 30
SCAN_MAX_ADAY     = 20
ANI_VOL_SPIKE_MIN = 2.0
ANI_PCT_MIN       = 1.5

# ════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
daily_pnl_lock  = threading.Lock()
recently_closed = {}
closed_lock     = threading.Lock()

# ════════════════════════════════════════════
# TELEGRAM BOT
# ════════════════════════════════════════════
bot = telebot.TeleBot(TELE_TOKEN)

def tg(msg):
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")

# ════════════════════════════════════════════
# SUPABASE
# ════════════════════════════════════════════
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        log.info("[SUPA] Bağlandı")
    except Exception as e:
        log.error(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try:
        supa.table("gpt_trades").insert(data).execute()
    except Exception as e:
        log.error(f"[SAVE] {e}")

# ════════════════════════════════════════════
# EXCHANGE
# ════════════════════════════════════════════
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})

_last_api = 0
_api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global _last_api
    for attempt in range(4):
        try:
            with _api_lock:
                wait = 0.5 - (time.time() - _last_api)
                if wait > 0: time.sleep(wait)
                _last_api = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except ccxt.NetworkError as e:
            log.warning(f"[API] Network: {e}"); time.sleep(3)
        except Exception as e:
            log.warning(f"[API] {attempt+1}: {e}"); time.sleep(2)
    return None

# ════════════════════════════════════════════
# PNL
# ════════════════════════════════════════════
def günlük_limit_asıldı():
    with daily_pnl_lock:
        return daily_pnl <= MAX_DAILY_LOSS

def pnl_ekle(miktar):
    global daily_pnl
    with daily_pnl_lock:
        daily_pnl += miktar
        return daily_pnl

def net_pnl_hesapla(pos, price):
    """Round-trip komisyon dahil NET pnl döner (giriş+çıkış masrafı düşülmüş)."""
    entry  = pos["entry"]
    amount = pos["amount"]
    side   = pos.get("side", "long")
    if side == "short":
        gross = (entry - price) * amount
    else:
        gross = (price - entry) * amount
    net = gross - ROUNDTRIP_FEE
    pct = (gross / (entry * amount)) * 100 if entry and amount else 0.0
    return net, pct

def fiyat_for_net(entry, amount, side, net_hedef):
    """Verilen net $ kâr/zarar hedefine denk gelen fiyatı hesaplar."""
    gross_hedef = net_hedef + ROUNDTRIP_FEE
    if side == "short":
        return entry - gross_hedef / amount
    return entry + gross_hedef / amount

# ════════════════════════════════════════════
# İNDİKATÖRLER
# ════════════════════════════════════════════
def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def filtre_15m(symbol):
    try:
        r = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=25)
        if not r or len(r) < 20:
            return False, {"red": "Veri yetersiz"}
        df = pd.DataFrame(r, columns=["t","o","h","l","c","v"])
        ma5  = float(df["c"].rolling(5).mean().iloc[-1])
        ma10 = float(df["c"].rolling(10).mean().iloc[-1])
        ma20 = float(df["c"].rolling(20).mean().iloc[-1])
        vol_ma5  = float(df["v"].rolling(5).mean().iloc[-1])
        vol_ma10 = float(df["v"].rolling(10).mean().iloc[-1])
        rsi = calc_rsi(df["c"])
        ma_ok  = ma5 > ma10 > ma20
        vol_ok = vol_ma5 > vol_ma10
        rsi_ok = RSI_MIN <= rsi <= RSI_MAX
        gecti = ma_ok and vol_ok and rsi_ok
        detay = {"ma5": round(ma5,8), "ma10": round(ma10,8), "ma20": round(ma20,8),
                  "vol_ma5": round(vol_ma5,0), "vol_ma10": round(vol_ma10,0),
                  "rsi": round(rsi,1), "ma_ok": ma_ok, "vol_ok": vol_ok, "rsi_ok": rsi_ok}
        return gecti, detay
    except Exception as e:
        log.warning(f"[FİLTRE] {symbol}: {e}")
        return False, {"red": str(e)}

# ════════════════════════════════════════════
# BORSA YARDIMCILARI
# ════════════════════════════════════════════
def borsa_hazirla(symbol):
    try: exchange.set_margin_mode("isolated", symbol, params={"marginCoin": "USDT"})
    except: pass
    try: exchange.set_leverage(LEVERAGE, symbol, params={"marginCoin": "USDT"})
    except: pass

def _pozisyon_var_mi(symbol, side):
    try:
        pos_list = safe_api(exchange.fetch_positions, [symbol])
        if pos_list:
            for p in pos_list:
                if float(p.get("contracts") or 0) > 0 and p.get("side") == side:
                    return float(p.get("entryPrice") or 0)
    except Exception as e:
        log.warning(f"[POS_CHECK] {symbol}: {e}")
    return None

def limit_giris(symbol, side, amount, ilk_fiyat):
    """SADECE LİMİT emirle giriş. GIRIS_DENEME kez, her seferinde güncel fiyata
    göre limiti yeniden konumlandırır. Doldurulamazsa None döner (market YOK)."""
    yon = "buy" if side == "long" else "sell"
    fiyat = ilk_fiyat

    for deneme in range(GIRIS_DENEME):
        try:
            fiyat_p = float(exchange.price_to_precision(symbol, fiyat))
            order = safe_api(
                exchange.create_order, symbol, "limit", yon, amount, fiyat_p,
                {"marginMode": "isolated", "marginCoin": "USDT", "timeInForce": "GTC"}
            )
        except Exception as e:
            log.warning(f"[GİRİŞ_LİMİT] {symbol}: {e}")
            order = None

        if not order:
            time.sleep(1)
            continue

        order_id = order.get("id")
        for _ in range(GIRIS_BEKLE_SN):
            time.sleep(1)
            durum = safe_api(exchange.fetch_order, order_id, symbol)
            if durum and durum.get("status") == "closed":
                avg = durum.get("average") or fiyat_p
                return float(avg)
            gercek = _pozisyon_var_mi(symbol, side)
            if gercek:
                return gercek

        try: safe_api(exchange.cancel_order, order_id, symbol)
        except: pass

        # Doldurulamadı — güncel fiyata göre limiti yenile
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t: continue
        guncel = float(t["last"])
        if side == "long":
            fiyat = round(guncel * (1 - GIRIS_OFFSET_PCT / 100), 8)
        else:
            fiyat = round(guncel * (1 + GIRIS_OFFSET_PCT / 100), 8)

    return None

def limit_kapat(symbol, side, amount, reason=""):
    """SADECE LİMİT emirle kapama. Her denemede fiyatı biraz daha agresifleştirir
    (spread'e doğru kayar) — hızlı dolum sağlar ama emir tipi hep LİMİT kalır."""
    kapat_yonu = "sell" if side == "long" else "buy"

    for deneme in range(KAPAT_DENEME):
        t = safe_api(exchange.fetch_ticker, symbol)
        if not t: 
            time.sleep(1); continue
        piyasa = float(t["last"])

        # Deneme arttıkça fiyatı piyasanın "kötü" tarafına doğru kaydırarak
        # dolma ihtimalini artırıyoruz (yine de LİMİT emir).
        agresiflik = KAPAT_ADIM_PCT * deneme
        if kapat_yonu == "sell":
            limit_fiyat = round(piyasa * (1 - agresiflik / 100), 8)
        else:
            limit_fiyat = round(piyasa * (1 + agresiflik / 100), 8)

        try:
            order = safe_api(
                exchange.create_order, symbol, "limit", kapat_yonu, amount, limit_fiyat,
                {"reduceOnly": True, "marginCoin": "USDT", "timeInForce": "GTC"}
            )
        except Exception as e:
            order = None
            if "22002" not in str(e) and "No position" not in str(e):
                log.warning(f"[KAPAT_LİMİT] {symbol}: {e}")

        if not order:
            time.sleep(1); continue

        order_id = order.get("id")
        for _ in range(KAPAT_BEKLE_SN):
            time.sleep(1)
            durum = safe_api(exchange.fetch_order, order_id, symbol)
            if durum and durum.get("status") == "closed":
                avg = durum.get("average") or durum.get("price") or limit_fiyat
                return float(avg)
            gercek = _pozisyon_var_mi(symbol, side)
            if not gercek:
                return limit_fiyat  # pozisyon borsada kapanmış

        try: safe_api(exchange.cancel_order, order_id, symbol)
        except: pass

    # Son çare: hâlâ pozisyon açıksa en agresif limit fiyatla son bir deneme
    t = safe_api(exchange.fetch_ticker, symbol)
    if t:
        piyasa = float(t["last"])
        son_agresiflik = KAPAT_ADIM_PCT * (KAPAT_DENEME + 3)
        if kapat_yonu == "sell":
            son_fiyat = round(piyasa * (1 - son_agresiflik / 100), 8)
        else:
            son_fiyat = round(piyasa * (1 + son_agresiflik / 100), 8)
        try:
            safe_api(exchange.create_order, symbol, "limit", kapat_yonu, amount, son_fiyat,
                     {"reduceOnly": True, "marginCoin": "USDT", "timeInForce": "GTC"})
            time.sleep(2)
        except: pass
        if not _pozisyon_var_mi(symbol, side):
            return son_fiyat
    return None

# ════════════════════════════════════════════
# SLOT
# ════════════════════════════════════════════
def pozisyon_slot_al(symbol, entry, sl, kaynak, mod="auto", side="long"):
    sym_base = symbol.split("/")[0].upper()
    max_open = MAX_OPEN_AUTO if mod == "auto" else MAX_OPEN_MANUEL

    with pos_lock:
        if symbol in positions: return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < RECENTLY_TTL:
                    return False
        if len(positions) >= max_open: return False
        if günlük_limit_asıldı(): return False

        positions[symbol] = {
            "entry": entry, "sl": sl,
            "tetiklendi": False, "floor_price": None,
            "max_price": entry, "min_price": entry,
            "open_time": time.time(), "amount": 0,
            "kaynak": kaynak, "mod": mod, "side": side, "pending": True,
        }
        return True

# ════════════════════════════════════════════
# İŞLEM AÇ — LONG (CoinSonar / Manuel / Tarayıcı)
# ════════════════════════════════════════════
def open_pos_auto(symbol, kaynak="coinsonar"):
    sym = symbol.split("/")[0]
    t0 = safe_api(exchange.fetch_ticker, symbol)
    if not t0: return False, "Fiyat alınamadı"
    price = float(t0["last"])
    sl = round(price * (1 - SL_PCT / 100), 8)

    if not pozisyon_slot_al(symbol, price, sl, kaynak, "auto" if kaynak != "manuel" else "manuel", "long"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / price, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            tg(f"📡 {sym} [{kaynak}] LİMİT giriş deneniyor @ ~{price:.8f}")
            giris_fiyat = round(price * (1 - GIRIS_OFFSET_PCT / 100), 8)
            gercek = limit_giris(symbol, "long", amount, giris_fiyat)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı, işlem iptal.")
                return

            sl_g = round(gercek * (1 - SL_PCT / 100), 8)
            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({"entry": gercek, "sl": sl_g, "amount": amount, "pending": False})

            tg(
                f"⚡ #{sym}USDT.P LONG\n"
                f"📡 Kaynak: {kaynak.upper()}\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_g:.8f} (-%{SL_PCT})\n"
                f"🎯 Net ${NET_TP_HEDEF:.2f} kâr trigger'ı sonrası trailing\n"
                f"💰 Pozisyon: {POS_SIZE}$ | Kaldıraç: {LEVERAGE}x"
            )
            log.info(f"[AÇIK] {sym} @ {gercek:.8f} [{kaynak}]")
        except Exception as e:
            log.error(f"[OPEN_AUTO] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM AÇ — SHORT (Manuel / Tarayıcı)
# ════════════════════════════════════════════
def open_pos_short_manuel(symbol, kaynak="manuel"):
    sym = symbol.split("/")[0]
    t0 = safe_api(exchange.fetch_ticker, symbol)
    if not t0: return False, "Fiyat alınamadı"
    price = float(t0["last"])
    sl = round(price * (1 + SL_PCT / 100), 8)

    if not pozisyon_slot_al(symbol, price, sl, kaynak, "manuel", "short"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / price, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            tg(f"📉 {sym} [{kaynak}] LİMİT short giriş deneniyor @ ~{price:.8f}")
            giris_fiyat = round(price * (1 + GIRIS_OFFSET_PCT / 100), 8)
            gercek = limit_giris(symbol, "short", amount, giris_fiyat)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı, işlem iptal.")
                return

            sl_g = round(gercek * (1 + SL_PCT / 100), 8)
            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({"entry": gercek, "sl": sl_g, "amount": amount,
                                               "min_price": gercek, "pending": False})

            tg(
                f"🔻 #{sym}USDT.P SHORT\n"
                f"📡 Kaynak: {kaynak.upper()}\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_g:.8f} (+%{SL_PCT})\n"
                f"🎯 Net ${NET_TP_HEDEF:.2f} kâr trigger'ı sonrası trailing\n"
                f"💰 Pozisyon: {POS_SIZE}$ | Kaldıraç: {LEVERAGE}x"
            )
            log.info(f"[AÇIK-SHORT] {sym} @ {gercek:.8f}")
        except Exception as e:
            log.error(f"[OPEN_SHORT] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM AÇ — FuturesKripto (giriş fiyatı sinyalden, SL/TP mantığımız uygulanır)
# ════════════════════════════════════════════
def open_pos_futureskripto(symbol, giris_sinyal):
    sym = symbol.split("/")[0]
    sl = round(giris_sinyal * (1 - SL_PCT / 100), 8)

    if not pozisyon_slot_al(symbol, giris_sinyal, sl, "futureskripto", "manuel", "long"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / giris_sinyal, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            tg(f"📡 {sym} [FuturesKripto] LİMİT giriş deneniyor @ {giris_sinyal:.8f}")
            gercek = limit_giris(symbol, "long", amount, giris_sinyal)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı, işlem iptal.")
                return

            sl_g = round(gercek * (1 - SL_PCT / 100), 8)
            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({"entry": gercek, "sl": sl_g, "amount": amount, "pending": False})

            tg(
                f"✅ #{sym}USDT.P LONG\n"
                f"📡 Kaynak: FUTURESKRIPTO\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_g:.8f} (-%{SL_PCT})\n"
                f"🎯 Net ${NET_TP_HEDEF:.2f} kâr trigger'ı sonrası trailing\n"
                f"💰 Pozisyon: {POS_SIZE}$ | Kaldıraç: {LEVERAGE}x"
            )
            log.info(f"[AÇIK] {sym} @ {gercek:.8f} [futureskripto]")
        except Exception as e:
            log.error(f"[FK_OPEN] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM KAPAT
# ════════════════════════════════════════════
def close_pos(symbol, reason):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    sym    = symbol.split("/")[0]
    side   = pos.get("side", "long")
    amount = pos.get("amount", 0)
    if not amount or amount <= 0:
        amount = round(POS_SIZE / pos["entry"], 4)

    # Gerçek borsa miktarını doğrula
    try:
        pos_list = safe_api(exchange.fetch_positions, [symbol])
        if pos_list:
            for p in pos_list:
                c = float(p.get("contracts") or 0)
                if c > 0 and p.get("side") == side:
                    amount = c; break
    except: pass

    exit_price = limit_kapat(symbol, side, amount, reason)
    if not exit_price:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = float(t["last"]) if t else pos["entry"]
        tg(f"⚠️ {sym} limit kapatma doğrulanamadı, tahmini fiyatla kayıt ediliyor.")

    net, pct = net_pnl_hesapla({**pos, "amount": amount}, exit_price)
    sure   = int((time.time() - pos["open_time"]) / 60)
    toplam = pnl_ekle(net)
    kaynak = pos.get("kaynak", "?")

    sym_base = sym.upper()
    with closed_lock:
        recently_closed[sym_base] = time.time()

    try:
        save_trade({"symbol": symbol, "signal": side.upper(), "pnl": round(net, 4),
                     "sure_dk": sure, "reason": reason, "kaynak": kaynak})
    except: pass

    if toplam <= MAX_DAILY_LOSS:
        tg(f"⛔ GÜNLÜK LİMİT! {toplam:+.2f}$")

    icon = "🟢" if net >= 0 else "🔴"
    tg(
        f"{icon} {sym.upper()} KAPANDI\n"
        f"{reason}\n"
        f"Net PnL: {net:+.2f}$ ({pct:+.2f}%) | {sure}dk\n"
        f"📡 {kaynak.upper()} | Günlük: {toplam:+.2f}$"
    )

# ════════════════════════════════════════════
# YÖNETİM DÖNGÜSÜ — TEK TP TRİGGER + KÂR FLOORU İLE TRAILING
# ════════════════════════════════════════════
def manage_loop():
    while True:
        time.sleep(1)
        try:
            with pos_lock:
                syms = list(positions.keys())
            if not syms: continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos or pos.get("pending"): continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = float(t["last"])

                entry  = pos["entry"]
                amount = pos.get("amount") or (POS_SIZE / entry)
                side   = pos.get("side", "long")
                sl     = pos["sl"]
                sym    = symbol.split("/")[0]

                net, pct = net_pnl_hesapla({**pos, "amount": amount}, price)
                sure = int((time.time() - pos["open_time"]) / 60)

                # ── Henüz trigger'a ulaşılmadıysa: SL kontrolü ──
                if not pos.get("tetiklendi"):
                    sl_tetiklendi = (price <= sl) if side == "long" else (price >= sl)
                    if sl_tetiklendi:
                        close_pos(symbol, f"🚫 SL ({sl:.8f})")
                        continue

                    if net >= NET_TP_HEDEF:
                        floor_price = fiyat_for_net(entry, amount, side, NET_TP_HEDEF)
                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["tetiklendi"] = True
                                positions[symbol]["floor_price"] = floor_price
                                positions[symbol]["max_price"] = price
                                positions[symbol]["min_price"] = price
                        tg(
                            f"🎯 {sym} net ${net:.2f} kâra ulaştı — TRAILING başladı\n"
                            f"Floor: {floor_price:.8f} (geri dönerse buradan net ${NET_TP_HEDEF:.2f} kilitlenir)"
                        )
                        continue

                # ── Trigger sonrası: trailing / floor kontrolü ──
                else:
                    floor_price = pos["floor_price"]
                    if side == "long":
                        if price > pos.get("max_price", entry):
                            with pos_lock:
                                if symbol in positions:
                                    positions[symbol]["max_price"] = price
                        if price <= floor_price:
                            close_pos(symbol, f"🎯 Trailing geri döndü, floor'dan kapandı (${NET_TP_HEDEF:.2f} net)")
                            continue
                    else:
                        if price < pos.get("min_price", entry):
                            with pos_lock:
                                if symbol in positions:
                                    positions[symbol]["min_price"] = price
                        if price >= floor_price:
                            close_pos(symbol, f"🎯 Trailing geri döndü, floor'dan kapandı (${NET_TP_HEDEF:.2f} net)")
                            continue

                # ── Süre kontrolü ──
                if sure >= MAX_SURE:
                    close_pos(symbol, f"⏰ Süre doldu ({MAX_SURE}dk)")
                    continue

                if günlük_limit_asıldı():
                    close_pos(symbol, "Günlük limit")
                    continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ════════════════════════════════════════════
# SİNYAL PARSE
# ════════════════════════════════════════════
def sinyal_parse(text):
    text_up = text.upper()
    match = re.search(r'#([A-Z0-9]+)USDT', text_up)
    if not match: match = re.search(r'\$([A-Z0-9]+)\s*\|', text_up)
    if not match: match = re.search(r'\b([A-Z]{2,10})USDT\b', text_up)
    if not match: return None
    coin_adi = match.group(1)

    giris = None
    for pattern in [r'Giri[şs]\s*Fiyat[ıi]\s*[:\s]+([0-9.]+)', r'LONG\s*\|\s*([0-9.]+)', r'Price[:\s]+([0-9.]+)']:
        m = re.search(pattern, text, re.IGNORECASE)
        if m: giris = float(m.group(1)); break

    return coin_adi, giris

# ════════════════════════════════════════════
# BAĞIMSIZ TARAYICI — ani pump/dump
# ════════════════════════════════════════════
def ani_hareket_tespit(symbol):
    try:
        r1m = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=25)
        if not r1m or len(r1m) < 15: return None, {}
        df = pd.DataFrame(r1m, columns=["t","o","h","l","c","v"])
        price = float(df["c"].iloc[-1])
        son_hacim = float(df["v"].iloc[-1])
        ort_hacim = float(df["v"].iloc[:-1].tail(20).mean())
        vol_oran  = son_hacim / max(ort_hacim, 0.0001)
        if vol_oran < ANI_VOL_SPIKE_MIN: return None, {"vol": round(vol_oran,1)}
        pct_3m = (price - float(df["c"].iloc[-4])) / float(df["c"].iloc[-4]) * 100

        r15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=20)
        if not r15m or len(r15m) < 15: return None, {}
        df15m = pd.DataFrame(r15m, columns=["t","o","h","l","c","v"])
        rsi = calc_rsi(df15m["c"])

        detay = {"vol": round(vol_oran,1), "pct": round(pct_3m,2), "price": price, "rsi": round(rsi,1)}
        if pct_3m >= ANI_PCT_MIN:
            if rsi > 75: return None, detay
            return "pump", detay
        elif pct_3m <= -ANI_PCT_MIN:
            if rsi > 50: return None, detay
            return "dump", detay
        return None, detay
    except Exception as e:
        log.warning(f"[ANİ] {symbol}: {e}")
        return None, {}

def scanner_loop():
    log.info("[SCANNER] Bağımsız pump/dump tarama başladı")
    while True:
        time.sleep(SCAN_INTERVAL)
        try:
            if günlük_limit_asıldı(): continue
            with pos_lock:
                if len(positions) >= MAX_OPEN_AUTO: continue

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers: continue

            adaylar = []
            for sym, t in tickers.items():
                if not sym.endswith("/USDT:USDT"): continue
                sym_base = sym.split("/")[0].upper()
                with pos_lock:
                    if sym in positions: continue
                    if any(ex.split("/")[0].upper() == sym_base for ex in positions): continue
                with closed_lock:
                    if sym_base in recently_closed and time.time() - recently_closed[sym_base] < RECENTLY_TTL:
                        continue
                last = t.get("last"); vol = t.get("quoteVolume") or 0; chg = abs(t.get("percentage") or 0)
                if not last or last < MIN_PRICE or last > MAX_PRICE: continue
                if vol < MIN_TURNOVER: continue
                adaylar.append((sym, chg))

            adaylar.sort(key=lambda x: x[1], reverse=True)
            adaylar = adaylar[:SCAN_MAX_ADAY]

            for sym, _ in adaylar:
                with pos_lock:
                    if len(positions) >= MAX_OPEN_AUTO: break
                yon, detay = ani_hareket_tespit(sym)
                if yon is None: continue
                sym_kisa = sym.split("/")[0]
                if yon == "pump":
                    tg(f"🚀 Ani PUMP: {sym_kisa} | Hacim:{detay['vol']}x | 3dk:{detay['pct']:+.1f}%\nLONG açılıyor...")
                    open_pos_auto(sym, "scanner")
                    break
                elif yon == "dump":
                    tg(f"📉 Ani DUMP: {sym_kisa} | Hacim:{detay['vol']}x | 3dk:{detay['pct']:+.1f}%\nSHORT açılıyor...")
                    open_pos_short_manuel(sym, "scanner")
                    break
        except Exception as e:
            log.error(f"[SCANNER] {e}")

# ════════════════════════════════════════════
# COINSONAR SİNYALİ İŞLE
# ════════════════════════════════════════════
def coinsonar_isle(text):
    text_up = text.upper()
    match = re.search(r'#([A-Z0-9]+)USDT', text_up)
    if not match: match = re.search(r'\$([A-Z0-9]+)\s*\|', text_up)
    if not match: return
    coin_adi = match.group(1)
    symbol = f"{coin_adi}/USDT:USDT"

    try:
        tickers = safe_api(exchange.fetch_tickers)
        if tickers and symbol not in tickers: return
    except: pass

    if günlük_limit_asıldı(): return
    with pos_lock:
        if len(positions) >= MAX_OPEN_AUTO: return
        if symbol in positions: return

    gecti, detay = filtre_15m(symbol)
    if gecti:
        tg(f"📡 CoinSonar: {coin_adi} ✅ filtre geçti, LİMİT giriş deneniyor...")
        open_pos_auto(symbol, "coinsonar")
    else:
        log.info(f"[COINSONAR] {coin_adi} ❌ PAS")

# ════════════════════════════════════════════
# TELETHON
# ════════════════════════════════════════════
async def telethon_loop():
    try:
        if TG_SESSION:
            client = TelegramClient(StringSession(TG_SESSION), TG_API_ID, TG_API_HASH)
        else:
            client = TelegramClient("sadik_session", TG_API_ID, TG_API_HASH)

        await client.start()
        log.info("[TELETHON] Bağlandı!")
        tg("📡 Telethon aktif — CoinSonar + FuturesKripto dinleniyor")

        @client.on(events.NewMessage(chats=[COINSONAR_KANAL, FUTURESKRIPTO_KANAL]))
        async def handler(event):
            text = event.message.text or ""
            chat = await event.get_chat()
            kanal = getattr(chat, "username", "") or ""

            if COINSONAR_KANAL.lower() in kanal.lower():
                threading.Thread(target=coinsonar_isle, args=(text,), daemon=True).start()
            elif FUTURESKRIPTO_KANAL.lower() in kanal.lower():
                sonuc = sinyal_parse(text)
                if sonuc:
                    coin_adi, giris = sonuc
                    if not giris: return
                    symbol = f"{coin_adi}/USDT:USDT"
                    try:
                        tickers = safe_api(exchange.fetch_tickers)
                        if tickers and symbol not in tickers: return
                    except: pass
                    if not günlük_limit_asıldı():
                        tg(f"📊 FuturesKripto: {coin_adi} | Giriş: {giris}")
                        threading.Thread(target=open_pos_futureskripto, args=(symbol, giris), daemon=True).start()

        await client.run_until_disconnected()
    except Exception as e:
        log.error(f"[TELETHON] {e}")
        tg(f"⚠️ Telethon bağlantı hatası: {e}")

def telethon_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telethon_loop())

# ════════════════════════════════════════════
# AÇILIŞTA POZİSYON YÜKLE
# ════════════════════════════════════════════
def load_open_positions():
    try:
        raw = safe_api(exchange.fetch_positions)
        if not raw: return
        yuklenen = 0
        lines = ["♻️ Pozisyonlar yüklendi:\n"]
        for p in raw:
            try:
                contracts = float(p.get("contracts") or 0)
                symbol = p.get("symbol", "")
                p_side = p.get("side", "")
                entry = float(p.get("entryPrice") or 0)
                if contracts == 0 or not symbol or p_side not in ("long","short") or entry == 0: continue
                sl = round(entry * (1 + SL_PCT/100), 8) if p_side == "short" else round(entry * (1 - SL_PCT/100), 8)
                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "entry": entry, "sl": sl, "tetiklendi": False, "floor_price": None,
                            "max_price": entry, "min_price": entry, "open_time": time.time(),
                            "amount": contracts, "kaynak": "yukle", "mod": "manuel",
                            "side": p_side, "pending": False,
                        }
                        yuklenen += 1
                        t = safe_api(exchange.fetch_ticker, symbol)
                        now = float(t["last"]) if t else entry
                        net, _ = net_pnl_hesapla(positions[symbol], now)
                        lines.append(f"{'🟢' if net>=0 else '🔴'} {symbol.split('/')[0]} [{p_side}] @ {entry:.8f} | {net:+.2f}$")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")
        if yuklenen > 0: tg("\n".join(lines))
        else: log.info("[YUKLE] Açık pozisyon yok")
    except Exception as e:
        log.error(f"[YUKLE] {e}")

# ════════════════════════════════════════════
# GÜNLÜK SIFIRLAMA
# ════════════════════════════════════════════
def gunluk_reset_loop():
    global daily_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now()
            yarin = (simdi + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            with daily_pnl_lock:
                eski = daily_pnl; daily_pnl = 0.0
            tg(f"🔄 Yeni gün! Dün: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}"); time.sleep(3600)

# ════════════════════════════════════════════
# HEALTH SERVER
# ════════════════════════════════════════════
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            with pos_lock: ps = ",".join(s.split("/")[0] for s in positions)
            with daily_pnl_lock: pnl = daily_pnl
            self.wfile.write(f"OK|pos:{len(positions)}({ps})|pnl:{pnl:+.2f}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ════════════════════════════════════════════
# TELEGRAM HANDLER (manuel komutlar)
# ════════════════════════════════════════════
def find_coin(text):
    words = re.findall(r"\b[A-Z]{2,10}\b", text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        for w in words:
            sym = f"{w}/USDT:USDT"
            if sym in tickers: return sym
    except: pass
    return None

@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    text = msg.text.strip()
    lower = text.lower()

    if "short ac" in lower or "short aç" in lower:
        coin = find_coin(text)
        if not coin:
            bot.send_message(msg.chat.id, "❌ Coin bulunamadı."); return
        coin_adi = coin.split("/")[0]
        if günlük_limit_asıldı():
            bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı."); return
        with pos_lock:
            if len(positions) >= MAX_OPEN_MANUEL:
                bot.send_message(msg.chat.id, "❌ Max pozisyon dolu."); return
            if coin in positions:
                bot.send_message(msg.chat.id, f"❌ {coin_adi} zaten açık."); return
        bot.send_message(msg.chat.id, f"📉 {coin_adi} SHORT — LİMİT giriş deneniyor...")
        open_pos_short_manuel(coin, "manuel")
        return

    if "long ac" in lower or "long aç" in lower:
        coin = find_coin(text)
        if not coin:
            bot.send_message(msg.chat.id, "❌ Coin bulunamadı."); return
        coin_adi = coin.split("/")[0]
        if günlük_limit_asıldı():
            bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı."); return
        with pos_lock:
            if len(positions) >= MAX_OPEN_MANUEL:
                bot.send_message(msg.chat.id, "❌ Max pozisyon dolu."); return
            if coin in positions:
                bot.send_message(msg.chat.id, f"❌ {coin_adi} zaten açık."); return
        bot.send_message(msg.chat.id, f"⚡ {coin_adi} LONG — LİMİT giriş deneniyor...")
        open_pos_auto(coin, "manuel")
        return

    if "/durum" in lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "📋 Açık pozisyon yok."); return
            lines = ["📋 POZİSYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = float(t["last"])
                amount = pos.get("amount") or (POS_SIZE / pos["entry"])
                net, pct = net_pnl_hesapla({**pos, "amount": amount}, price)
                sure = int((time.time() - pos["open_time"]) / 60)
                durum_str = "TRAILING 🎯" if pos.get("tetiklendi") else f"SL:{pos['sl']:.8f}"
                lines.append(
                    f"{'🟢' if net>=0 else '🔴'} {sym.split('/')[0]} [{pos.get('side','long').upper()}/{pos.get('kaynak','?')}]\n"
                    f"   {pos['entry']:.8f}→{price:.8f}\n"
                    f"   Net:{net:+.2f}$ ({pct:+.2f}%) | {sure}dk | {durum_str}\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    if "/istatistik" in lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r = supa.table("gpt_trades").select("pnl,kaynak").execute()
            data = r.data or []
            if not data:
                bot.send_message(msg.chat.id, "Kayıt yok."); return
            toplam = len(data)
            kazan = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net = sum(float(d.get("pnl") or 0) for d in data)
            with daily_pnl_lock: gunluk = daily_pnl
            bot.send_message(msg.chat.id,
                f"📊 İSTATİSTİK\nToplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net: {net:+.2f}$ | Günlük: {gunluk:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    if "kapat" in lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Açık pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            if symbol.split("/")[0].upper() in text.upper() or "hepsi" in lower:
                threading.Thread(target=close_pos, args=(symbol, "Kullanıcı isteği"), daemon=True).start()
                kapatildi = True
        if not kapatildi:
            bot.send_message(msg.chat.id, f"Hangisini? {', '.join(s.split('/')[0] for s in syms)}")
        return

    coin = find_coin(text)
    if coin:
        sym = coin.split("/")[0]
        gecti, detay = filtre_15m(coin)
        bot.send_message(msg.chat.id,
            f"📊 {sym} 15m ANALİZ\nMA Sırası: {'✅' if detay.get('ma_ok') else '❌'}\n"
            f"Hacim: {'✅' if detay.get('vol_ok') else '❌'}\n"
            f"RSI(14): {detay.get('rsi',0):.1f} {'✅' if detay.get('rsi_ok') else '❌'}\n\n"
            f"{'✅ GİRİLİR' if gecti else '❌ PAS'}")
        return

    bot.send_message(msg.chat.id,
        "Komutlar:\n/durum — Açık pozisyonlar\n/istatistik — Geçmiş işlemler\n"
        "COIN long aç — Manuel LONG\nCOIN short aç — Manuel SHORT\n"
        "COIN kapat / hepsi kapat")

# ════════════════════════════════════════════
# SHUTDOWN
# ════════════════════════════════════════════
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    if syms: tg(f"⏸ Yeniden başlıyor...\n{len(syms)} pozisyon açık.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT, shutdown)

# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("SADIK SCALP FAST BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=telethon_thread, daemon=True).start()

    tg(
        "🚀 SADIK SCALP FAST\n\n"
        "📡 Kaynaklar: CoinSonar V2 | FuturesKripto | Manuel | Tarayıcı\n\n"
        f"💰 Pozisyon: {MARGIN}$ margin × {LEVERAGE}x = {POS_SIZE}$\n"
        f"🚫 SL: -%{SL_PCT}\n"
        f"🎯 Net ${NET_TP_HEDEF:.2f} kâr trigger'ı → trailing → geri dönerse floor'dan kapanır\n"
        f"📐 Giriş/Çıkış: SADECE LİMİT emir\n\n"
        "Komutlar:\n/durum | /istatistik\nCOIN long aç | COIN short aç | COIN kapat"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
