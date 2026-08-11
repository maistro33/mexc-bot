#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
SWING REVERSAL BOT v1.1 — 11 Ağustos 2026
"Düşükten al, yüksekten sat" — SADECE FİYAT AKSİYONU.
Hiçbir indikatör yok (RSI/ADX/MACD/hacim YOK). Mantık:
  - LONG: fiyat son LOOKBACK mumun EN DÜŞÜĞÜNÜ yaptı, sonra
    bir sonraki mum yukarı kapandı (dip + dönüş onayı)
  - SHORT: fiyat son LOOKBACK mumun EN YÜKSEĞİNİ yaptı, sonra
    bir sonraki mum aşağı kapandı (tepe + dönüş onayı)
SL swing noktasının biraz ötesine konur (GENİŞ - kullanıcı
talebiyle), TP basit sabit R çarpanı ile (karmaşık trailing
kademe YOK - "basit etkili" isteği).

⚠️ DÜRÜSTLÜK NOTU: Bu mantık HİÇ backtest edilmedi. Önceki
scalp botunun (v5.23/24) "trend kovala" mantığı 287 gerçek
işlemde simetrik sonuç verdi (+%3.34 kazanç / -%3.44 kayıp,
gerçek edge yoktu). Bu YENİ ve FARKLI bir hipotez (tersine
dönüş yakalamak, trend kovalamak değil) - performansı sadece
canlı veri toplayarak öğreneceğiz.

v1.1 DEĞİŞİKLİKLER:
  - Hard SL emri kaldırıldı, İZOLE MARJİN kullanılıyor - kayıp
    en kötü ihtimalle marjine (~$1) yakın kalıyor, fiyat
    seviyesi bazlı SL yok.
  - Coin engelleme eklendi (scalp_bot v5.24 ile aynı mekanizma):
    /blokla, /blokkaldir, /blokeliste komutları - kalıcı diske
    kaydediliyor, pozisyon açma noktasında kontrol ediliyor.
════════════════════════════════════════════════════════
"""

import os
import time
import json
import logging
import threading
import ccxt
import telebot
import pandas as pd
import numpy as np
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                     stream=sys.stdout, force=True)
log = logging.getLogger("SWING_BOT")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY = os.getenv("BITGET_API", "")
API_SEC = os.getenv("BITGET_SEC", "")
PASSPHRASE = os.getenv("BITGET_PASS", "")

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni eksik.")
if not CHAT_ID:
    raise RuntimeError("MY_CHAT_ID ortam değişkeni eksik - yetki kontrolü için ZORUNLU.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None


def tg(msg):
    if not bot or not CHAT_ID:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


def yetkili_mi(msg_or_call):
    try:
        chat_id = msg_or_call.message.chat.id if hasattr(msg_or_call, "message") else msg_or_call.chat.id
    except Exception:
        return False
    if chat_id != CHAT_ID:
        return False
    return True


SLUGGISH_BASE = {"BTC", "ETH", "XRP", "ADA", "DOGE", "BNB", "TRX", "LINK", "LTC", "BCH"}

# ── SİNYAL PARAMETRESİ — SADECE FİYAT AKSİYONU ──
LOOKBACK = int(os.getenv("LOOKBACK", "20"))
# swing dip/tepe kaç mumluk pencerede aranıyor (5m mum, 20 = 100dk)

# ── SL/TP — GENİŞ SL (kullanıcı talebi) ──
SL_BUFFER_PCT = float(os.getenv("SL_BUFFER_PCT", "0.015"))
# swing noktasının %1.5 ötesine SL konur (ekstra güvenlik payı)
MAX_SL_PCT = float(os.getenv("MAX_SL_PCT", "0.08"))
# SL çok uzaklaşırsa (oynak coin) tavan - "geniş ama sınırsız değil"
MIN_SL_PCT = float(os.getenv("MIN_SL_PCT", "0.03"))
# SL çok dar olursa (durgun coin) taban - normal gürültüyle erken çıkmasın

TP_R_ORANI = float(os.getenv("TP_R_ORANI", "1.5"))
# basit sabit TP - riskin 1.5 katı kârda kapan (trailing kademe YOK, "basit etkili")

COOLDOWN_SAAT = float(os.getenv("COOLDOWN_SAAT", "1.0"))
MAX_HOLD_SAAT = float(os.getenv("MAX_HOLD_SAAT", "24"))

LEV = int(os.getenv("LEV", "10"))
SABIT_MARJIN_USDT = float(os.getenv("SABIT_MARJIN_USDT", "1"))
MAX_POS = int(os.getenv("MAX_POS", "2"))
# kullanıcı Railway'den ayarlayacak

ADAY_HAVUZU_BUYUKLUGU = int(os.getenv("ADAY_HAVUZU_BUYUKLUGU", "80"))
TARAMA_PARALEL_WORKER = int(os.getenv("TARAMA_PARALEL_WORKER", "5"))
KONTROL_ARALIGI_SN = 60
GOSTERGE_MUM_5M = LOOKBACK + 10

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/swing_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/swing_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/swing_log.json")

trade_state = {}
state_lock = threading.Lock()
acilis_rezervasyonlari = {}
trade_log = []
log_lock = threading.Lock()

# Coin engelleme - scalp_bot v5.24'teki aynı mekanizma
BLOKE_PATH = os.getenv("BLOKE_PATH", "/data/swing_bloke.json")
bloke_coinler = set()
bloke_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()


def atomik_yaz(path, veri):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(veri, f)
        os.replace(tmp, path)
    except Exception as e:
        log.warning(f"[ATOMIK_YAZ] {path}: {e}")


def guvenli_oku(path, varsayilan):
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"[OKU] {path}: {e}")
    return varsayilan


def durumu_diske_yaz():
    with state_lock:
        veri = dict(trade_state)
    atomik_yaz(TRADE_STATE_PATH, veri)


def durumu_diskten_yukle():
    global trade_state
    trade_state = guvenli_oku(TRADE_STATE_PATH, {})


def cooldown_diske_yaz():
    with cooldown_lock:
        veri = dict(son_kapanis_zamani)
    atomik_yaz(COOLDOWN_PATH, veri)


def cooldown_diskten_yukle():
    global son_kapanis_zamani
    son_kapanis_zamani = guvenli_oku(COOLDOWN_PATH, {})


def trade_log_kaydet(kayit):
    with log_lock:
        trade_log.append(kayit)
        veri = list(trade_log)
    atomik_yaz(TRADE_LOG_PATH, veri)


def trade_log_yukle():
    global trade_log
    trade_log = guvenli_oku(TRADE_LOG_PATH, [])


def bloke_diske_yaz():
    with bloke_lock:
        veri = sorted(bloke_coinler)
    atomik_yaz(BLOKE_PATH, veri)


def bloke_diskten_yukle():
    global bloke_coinler
    bloke_coinler = set(guvenli_oku(BLOKE_PATH, []))


def coin_bloke_mi(sym):
    baz = sym.split("/")[0].upper()
    with bloke_lock:
        return baz in bloke_coinler


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def get_df(sym, tf, limit=60):
    for deneme in range(3):
        try:
            candles = exchange.fetch_ohlcv(sym, tf, limit=limit + 1)
            if not candles or len(candles) < 2:
                return None
            candles = candles[:-1]  # son (kapanmamış) mumu at
            df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
            time.sleep(0.08)
            return df
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                time.sleep(1.5 * (deneme + 1))
                continue
            log.warning(f"[VERI] {sym} {tf}: {e}")
            return None
    return None


def cooldown_da_mi(sym):
    with cooldown_lock:
        son = son_kapanis_zamani.get(sym)
    if son is None:
        return False
    return (time.time() - son) < COOLDOWN_SAAT * 3600


# ════════════════════════════════════════════
# ADAY HAVUZU
# ════════════════════════════════════════════
def aday_havuzu():
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
        return []
    markets = None
    try:
        markets = exchange.load_markets()
    except Exception:
        pass
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE:
            continue
        if markets:
            m = markets.get(sym)
            if m and m.get("info", {}).get("isRwa") == "YES":
                continue
        vol = t.get("quoteVolume") or 0
        if vol < 300000:
            continue
        chg = t.get("percentage")
        if chg is None:
            continue
        skor = abs(chg) * np.log10(max(vol, 10))
        adaylar.append((sym, skor))
    adaylar.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in adaylar[:ADAY_HAVUZU_BUYUKLUGU]]


# ════════════════════════════════════════════
# SİNYAL — SADECE FİYAT AKSİYONU
# ════════════════════════════════════════════
def swing_sinyal(sym):
    """LONG: son LOOKBACK mumun en düşüğü SON MUMDAN ÖNCEKİ bir mumda
    yapıldı VE son mum yukarı kapandı (close > open, dönüş onayı).
    SHORT: aynı mantık tersten (tepe + aşağı dönüş).
    Hiçbir indikatör kullanılmıyor - sadece high/low/close karşılaştırması."""
    df = get_df(sym, "5m", GOSTERGE_MUM_5M)
    if df is None or len(df) < LOOKBACK + 2:
        return None

    pencere = df.iloc[-(LOOKBACK + 1):-1]  # son mum hariç, ondan önceki LOOKBACK mum
    son_mum = df.iloc[-1]

    swing_low = pencere["low"].min()
    swing_high = pencere["high"].max()

    # LONG: dip yakın zamanda yapıldı (pencerenin son 3 mumu içinde) VE
    # şu anki mum yukarı kapandı VE mumun kapanışı dipten belirgin yukarıda
    dip_idx = pencere["low"].idxmin()
    son_3_idx = pencere.index[-3:]
    dip_yakin_zamanli = dip_idx in son_3_idx
    son_yukari_kapandi = son_mum["close"] > son_mum["open"]

    if dip_yakin_zamanli and son_yukari_kapandi and son_mum["close"] > swing_low:
        return {"symbol": sym, "entry": float(son_mum["close"]), "yon": "long",
                "swing_nokta": float(swing_low), "tetik_ts": int(son_mum["ts"])}

    tepe_idx = pencere["high"].idxmax()
    tepe_yakin_zamanli = tepe_idx in son_3_idx
    son_asagi_kapandi = son_mum["close"] < son_mum["open"]

    if tepe_yakin_zamanli and son_asagi_kapandi and son_mum["close"] < swing_high:
        return {"symbol": sym, "entry": float(son_mum["close"]), "yon": "short",
                "swing_nokta": float(swing_high), "tetik_ts": int(son_mum["ts"])}

    return None


# ════════════════════════════════════════════
# HESAP / İŞLEM AÇICI
# ════════════════════════════════════════════
def gercek_bakiye_al():
    try:
        bakiye = exchange.fetch_balance()
        return safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] {e}")
        return None


def sembol_max_kaldirac(sym, istenen_lev):
    try:
        markets = exchange.load_markets()
        m = markets.get(sym)
        if not m:
            return istenen_lev
        max_lev = (m.get("limits", {}) or {}).get("leverage", {}).get("max")
        if max_lev is None:
            return istenen_lev
        return min(istenen_lev, int(max_lev))
    except Exception:
        return istenen_lev


def acilis_basarisiz_cooldown_uygula(sym):
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()


def pozisyon_ac(sinyal):
    sym = sinyal["symbol"]
    entry = sinyal["entry"]
    yon = sinyal["yon"]
    swing_nokta = sinyal["swing_nokta"]

    # scalp_bot v5.24'teki aynı mekanizma: kullanıcı kontrollü kalıcı
    # coin engelleme - tek ortak açılış noktasında kontrol ediliyor.
    if coin_bloke_mi(sym):
        log.info(f"[COIN_BLOKE] {sym} kullanıcı tarafından engellenmiş, açılış atlanıyor")
        return

    with state_lock:
        if sym in trade_state:
            return
        acik_sayi = len(trade_state) + len(acilis_rezervasyonlari)
        if acik_sayi >= MAX_POS:
            return
        acilis_rezervasyonlari[sym] = True

    try:
        _pozisyon_ac_ic(sym, entry, yon, swing_nokta)
    finally:
        with state_lock:
            acilis_rezervasyonlari.pop(sym, None)


def _pozisyon_ac_ic(sym, entry, yon, swing_nokta):
    if cooldown_da_mi(sym):
        return

    bakiye = gercek_bakiye_al()
    if bakiye is None or bakiye <= 0:
        acilis_basarisiz_cooldown_uygula(sym)
        return

    # KULLANICI KARARI: hard SL emri yerine İZOLE MARJİN kullanılıyor.
    # Mantık: izole modda pozisyon başına ayrılan marjin ($1) borsa
    # tarafından kilitlenir - pozisyon o marjinin tamamını (yaklaşık)
    # kaybedince borsa OTOMATİK likide eder. Yani "SL" artık bir fiyat
    # seviyesi değil, marjinin kendisi - kayıp yaklaşık $1'i (+ küçük
    # likidasyon ücreti) aşamaz, fiyat ne kadar aleyhe giderse gitsin.
    # ⚠️ DÜRÜSTLÜK NOTU: bu TAM OLARAK $1.00 garantisi değil - likidasyon
    # ücreti ve (pozisyon uzun süre açık kalırsa) funding oranı küçük bir
    # ek maliyet oluşturabilir, ama kayıp pratikte marjine çok yakın kalır.
    # Ayrıca artık fiyat bazlı bir SL emri YOK - pozisyon likide olana ya
    # da TP'ye ulaşana ya da MAX_HOLD_SAAT dolup manuel kapanana kadar
    # açık kalabilir.
    try:
        exchange.set_margin_mode("isolated", sym)
    except Exception as e:
        log.warning(f"[MARJIN_MODU] {sym}: izole moda geçilemedi (görmezden geliniyor, muhtemelen zaten izole): {e}")

    # TP hesaplaması için hâlâ bir referans "risk" mesafesine ihtiyaç var -
    # swing noktası bu referansı veriyor (SL emri konmasa da TP oranı bu
    # mesafeye göre hesaplanıyor), taban/tavan sınırları koruma amaçlı.
    if yon == "long":
        sl_referans = swing_nokta * (1 - SL_BUFFER_PCT)
        sl_mesafe_pct = (entry - sl_referans) / entry
        sl_mesafe_pct = max(MIN_SL_PCT, min(MAX_SL_PCT, sl_mesafe_pct))
    else:
        sl_referans = swing_nokta * (1 + SL_BUFFER_PCT)
        sl_mesafe_pct = (sl_referans - entry) / entry
        sl_mesafe_pct = max(MIN_SL_PCT, min(MAX_SL_PCT, sl_mesafe_pct))

    if sl_mesafe_pct <= 0:
        acilis_basarisiz_cooldown_uygula(sym)
        return

    LEV_KULLANILAN = sembol_max_kaldirac(sym, LEV)
    notional = SABIT_MARJIN_USDT * LEV_KULLANILAN
    amount = notional / entry

    try:
        qty = float(exchange.amount_to_precision(sym, amount))
    except Exception as e:
        log.warning(f"[MIKTAR] {sym}: {e}")
        acilis_basarisiz_cooldown_uygula(sym)
        return
    if qty <= 0:
        acilis_basarisiz_cooldown_uygula(sym)
        return

    try:
        exchange.set_leverage(LEV_KULLANILAN, sym)
        time.sleep(0.3)
    except Exception as e:
        log.warning(f"[KALDIRAC] {sym}: {e}")

    emir_yonu = "buy" if yon == "long" else "sell"
    try:
        exchange.create_market_order(sym, emir_yonu, qty)
    except Exception as e:
        tg(f"⚠️ {sym} giriş emri başarısız: {e}")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    time.sleep(0.8)
    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
    except Exception:
        gercek_pos = None

    if gercek_pos and safe(gercek_pos.get("entryPrice")) > 0:
        entry = safe(gercek_pos.get("entryPrice"))

    sl_referans_gercek = entry * (1 - sl_mesafe_pct) if yon == "long" else entry * (1 + sl_mesafe_pct)
    r_risk = abs(entry - sl_referans_gercek)
    tp = entry + r_risk * TP_R_ORANI if yon == "long" else entry - r_risk * TP_R_ORANI
    kapatma_yonu = "sell" if yon == "long" else "buy"

    # Hard SL emri KONMUYOR (kullanıcı kararı) - izole marjin likidasyonu
    # kayıp sınırı görevi görüyor. Sadece TP emri konuyor.
    tp_emir_id = None
    tp_fiyat = float(exchange.price_to_precision(sym, tp))
    try:
        tp_emri = exchange.create_order(sym, "limit", kapatma_yonu, qty, tp_fiyat,
                                         {"reduceOnly": True})
        tp_emir_id = tp_emri.get("id")
    except Exception as e:
        log.warning(f"[TP] {sym}: {e}")

    with state_lock:
        trade_state[sym] = {
            "entry": entry, "sl_referans": sl_referans_gercek, "tp": tp,
            "sl_emir_id": None, "tp_emir_id": tp_emir_id,
            "qty": qty, "yon": yon, "acilis_zamani": time.time(),
        }
    durumu_diske_yaz()

    yon_etiket = "LONG (dipten)" if yon == "long" else "SHORT (tepeden)"
    tg(f"📈 SWING POZİSYON: {sym} {yon_etiket} [İZOLE MARJİN]\n"
       f"Giriş≈{entry:.6f} | TP:{tp_fiyat:.6f} ({TP_R_ORANI}R)\n"
       f"Hard SL YOK - izole marjin likidasyonu kayıp sınırı: en kötü ihtimalle ≈${SABIT_MARJIN_USDT:.2f} kayıp\n"
       f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Marjin: ${SABIT_MARJIN_USDT:.2f}")


def pozisyonu_kapat(sym, sebep="manuel"):
    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
        with state_lock:
            durum = trade_state.get(sym)

        if not gercek_pos:
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            with cooldown_lock:
                son_kapanis_zamani[sym] = time.time()
            cooldown_diske_yaz()
            if durum:
                cikis_fiyat = None
                for emir_id in (durum.get("sl_emir_id"), durum.get("tp_emir_id")):
                    if not emir_id:
                        continue
                    try:
                        detay = exchange.fetch_order(emir_id, sym)
                        if detay.get("status") in ("closed", "filled"):
                            dolum = safe(detay.get("average")) or safe(detay.get("price"))
                            if dolum > 0:
                                cikis_fiyat = dolum
                                break
                    except Exception:
                        pass
                if not cikis_fiyat:
                    try:
                        t = exchange.fetch_ticker(sym)
                        cikis_fiyat = safe(t["last"])
                    except Exception:
                        cikis_fiyat = durum["entry"]
                entry = durum["entry"]
                qty = durum.get("qty", 0)
                yon = durum.get("yon", "long")
                pnl = (cikis_fiyat - entry) * qty if yon == "long" else (entry - cikis_fiyat) * qty
                trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat, "pnl": pnl,
                                   "yon": yon, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                                   "not": f"{sebep}_borsada_onceden_kapanmis"})
                tg(f"ℹ️ {sym} borsada zaten kapanmıştı. Tahmini PnL≈{pnl:+.2f}$ kaydedildi.")
            return True, "kapatildi"

        qty = safe(gercek_pos.get("contracts"))
        entry_fiyat = safe(gercek_pos.get("entryPrice"))
        pozisyon_yonu = gercek_pos.get("side", "long")
        kapama_yon = "sell" if pozisyon_yonu == "long" else "buy"

        if durum:
            for emir_id in (durum.get("sl_emir_id"), durum.get("tp_emir_id")):
                if emir_id:
                    try:
                        exchange.cancel_order(emir_id, sym)
                    except Exception:
                        pass

        kapama_emri = exchange.create_market_order(sym, kapama_yon, qty, params={"reduceOnly": True})
        time.sleep(1)
        cikis_fiyat = None
        try:
            detay = exchange.fetch_order(kapama_emri.get("id"), sym)
            dolum = safe(detay.get("average")) or safe(detay.get("price"))
            if dolum > 0:
                cikis_fiyat = dolum
        except Exception:
            pass
        if not cikis_fiyat:
            try:
                t = exchange.fetch_ticker(sym)
                cikis_fiyat = safe(t["last"])
            except Exception:
                cikis_fiyat = entry_fiyat

        pnl = (cikis_fiyat - entry_fiyat) * qty if pozisyon_yonu == "long" else (entry_fiyat - cikis_fiyat) * qty
        trade_log_kaydet({"symbol": sym, "entry": entry_fiyat, "exit": cikis_fiyat, "pnl": pnl,
                           "yon": pozisyon_yonu, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                           "not": sebep})
        with state_lock:
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        with cooldown_lock:
            son_kapanis_zamani[sym] = time.time()
        cooldown_diske_yaz()
        return True, f"✅ {sym} kapatıldı | PnL≈{pnl:+.2f}$"
    except Exception as e:
        return False, f"⚠️ {sym} kapatma hatası: {e}"


# ════════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════════
if bot:
    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            durumlar = dict(trade_state)
        if not durumlar:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        satirlar = ["📋 AÇIK POZİSYON(LAR)\n"]
        for sym, d in durumlar.items():
            try:
                t = exchange.fetch_ticker(sym)
                guncel = safe(t["last"])
                pnl_pct = (guncel - d["entry"]) / d["entry"] * 100 if d["yon"] == "long" else (d["entry"] - guncel) / d["entry"] * 100
                etiket = "LONG" if d["yon"] == "long" else "SHORT"
                satirlar.append(f"{sym} {etiket}\n   Giriş:{d['entry']:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                                 f"   TP:{d['tp']:.6f} | Hard SL yok (izole marjin, max kayıp≈${SABIT_MARJIN_USDT:.2f})")
            except Exception:
                satirlar.append(f"{sym} (fiyat alınamadı)")
        bot.send_message(msg.chat.id, "\n".join(satirlar))

    @bot.message_handler(commands=["kapat"])
    def kapat_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            acik = list(trade_state.keys())
        if not acik:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        parca = msg.text.replace("/kapat", "", 1).strip().upper()
        if parca:
            hedef = next((s for s in acik if s.split("/")[0] == parca), None)
            if not hedef:
                bot.send_message(msg.chat.id, f"'{parca}' bulunamadı: {acik}")
                return
        else:
            if len(acik) > 1:
                bot.send_message(msg.chat.id, f"Birden fazla pozisyon var: {acik}")
                return
            hedef = acik[0]
        bot.send_message(msg.chat.id, f"⏳ {hedef} kapatılıyor...")
        basari, mesaj = pozisyonu_kapat(hedef)
        bot.send_message(msg.chat.id, mesaj)

    @bot.message_handler(commands=["ozet"])
    def ozet_komutu(msg):
        if not yetkili_mi(msg):
            return
        with log_lock:
            gecmis = list(trade_log)
        satirlar = ["📊 SWING BOT ÖZET\n"]
        try:
            bakiye_bilgi = exchange.fetch_balance()
            usdt = bakiye_bilgi.get("USDT", {})
            toplam = safe(usdt.get("total", 0)) or safe(usdt.get("free", 0))
            satirlar.append(f"💰 Bakiye: {toplam:.2f}$")
        except Exception:
            pass
        if gecmis:
            toplam_islem = len(gecmis)
            kazanan = [t for t in gecmis if t["pnl"] > 0]
            net = sum(t["pnl"] for t in gecmis)
            satirlar.append(f"Toplam: {toplam_islem} | Kazanma: %{len(kazanan)/toplam_islem*100:.1f} | Net: {net:+.2f}$")
            uzun = [t for t in gecmis if t.get("yon") == "long"]
            kisa = [t for t in gecmis if t.get("yon") == "short"]
            if uzun:
                w = len([t for t in uzun if t["pnl"] > 0])
                satirlar.append(f"LONG: {len(uzun)} işlem, %{w/len(uzun)*100:.0f} kazanma, net {sum(t['pnl'] for t in uzun):+.2f}$")
            if kisa:
                w = len([t for t in kisa if t["pnl"] > 0])
                satirlar.append(f"SHORT: {len(kisa)} işlem, %{w/len(kisa)*100:.0f} kazanma, net {sum(t['pnl'] for t in kisa):+.2f}$")
        else:
            satirlar.append("Henüz kapanan işlem yok.")
        with state_lock:
            satirlar.append(f"\nAçık pozisyon: {len(trade_state)}/{MAX_POS}")
        bot.send_message(msg.chat.id, "\n".join(satirlar))

    @bot.message_handler(commands=["veri"])
    def veri_komutu(msg):
        if not yetkili_mi(msg):
            return
        with log_lock:
            veri = list(trade_log)
        if not veri:
            bot.send_message(msg.chat.id, "Henüz kapanan işlem yok.")
            return
        try:
            import io
            icerik = json.dumps(veri, ensure_ascii=False, indent=2)
            dosya = io.BytesIO(icerik.encode("utf-8"))
            dosya.name = f"swing_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
            bot.send_document(msg.chat.id, dosya, caption=f"📦 {len(veri)} işlem")
        except Exception as e:
            bot.send_message(msg.chat.id, f"⚠️ Hata: {e}")

    # scalp_bot v5.24'teki aynı coin engelleme mekanizması - buton listesine
    # bağımlı kalmadan doğrudan yazarak engelleyip kaldırabilmek için.
    @bot.message_handler(commands=["blokla"])
    def blokla_komutu(msg):
        if not yetkili_mi(msg):
            return
        parca = msg.text.replace("/blokla", "", 1).strip().upper()
        if not parca:
            bot.send_message(msg.chat.id, "Kullanım: /blokla COIN_ADI (örnek: /blokla POWER)")
            return
        with bloke_lock:
            bloke_coinler.add(parca)
        bloke_diske_yaz()
        bot.send_message(msg.chat.id, f"🚫 {parca} engellendi. Kaldırmak için: /blokkaldir {parca}")

    @bot.message_handler(commands=["blokkaldir"])
    def blokkaldir_komutu(msg):
        if not yetkili_mi(msg):
            return
        parca = msg.text.replace("/blokkaldir", "", 1).strip().upper()
        if not parca:
            bot.send_message(msg.chat.id, "Kullanım: /blokkaldir COIN_ADI (örnek: /blokkaldir POWER)")
            return
        with bloke_lock:
            vardi = parca in bloke_coinler
            bloke_coinler.discard(parca)
        bloke_diske_yaz()
        if vardi:
            bot.send_message(msg.chat.id, f"✅ {parca} engeli kaldırıldı.")
        else:
            bot.send_message(msg.chat.id, f"ℹ️ {parca} zaten engelli değildi.")

    @bot.message_handler(commands=["blokeliste"])
    def blokeliste_komutu(msg):
        if not yetkili_mi(msg):
            return
        with bloke_lock:
            liste = sorted(bloke_coinler)
        if liste:
            bot.send_message(msg.chat.id, "🚫 Engelli coinler:\n" + ", ".join(liste))
        else:
            bot.send_message(msg.chat.id, "Şu an engelli coin yok.")


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
            time.sleep(5)


# ════════════════════════════════════════════
# YÖNETİM DÖNGÜSÜ (SL/TP takip)
# ════════════════════════════════════════════
def manage_loop():
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            if not semboller:
                time.sleep(5)
                continue
            for sym in semboller:
                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue
                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    tg(f"⏱️ {sym} — max tutma süresi aşıldı, kapatılıyor")
                    pozisyonu_kapat(sym, sebep="max_hold_timeout")
                    continue
                try:
                    pozlar = exchange.fetch_positions([sym])
                    gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
                except Exception as e:
                    log.warning(f"[MANAGE] {sym}: {e}")
                    continue
                if not gercek_pos:
                    # Pozisyon borsada artık yok - ya TP emri doldu, ya da
                    # (hard SL emri hiç konmadığı için) izole marjin
                    # LİKİDE ETTİ. TP dolum kaydı varsa "tp_dolu", yoksa
                    # "izole_marjin_likidasyonu" olarak etiketleniyor.
                    entry = durum["entry"]
                    qty = durum.get("qty", 0)
                    yon = durum.get("yon", "long")
                    cikis_fiyat = None
                    sebep_etiket = "izole_marjin_likidasyonu"
                    tp_id = durum.get("tp_emir_id")
                    if tp_id:
                        try:
                            detay = exchange.fetch_order(tp_id, sym)
                            if detay.get("status") in ("closed", "filled"):
                                dolum = safe(detay.get("average")) or safe(detay.get("price"))
                                if dolum > 0:
                                    cikis_fiyat = dolum
                                    sebep_etiket = "tp_dolu"
                        except Exception:
                            pass
                    if not cikis_fiyat:
                        try:
                            t = exchange.fetch_ticker(sym)
                            cikis_fiyat = safe(t["last"])
                        except Exception:
                            cikis_fiyat = entry
                    pnl = (cikis_fiyat - entry) * qty if yon == "long" else (entry - cikis_fiyat) * qty
                    if sebep_etiket == "izole_marjin_likidasyonu":
                        # likidasyonda gerçek kayıp marjine yakındır - tahmini
                        # PnL yerine marjini kayıp olarak kaydetmek daha
                        # doğru bir yaklaşım (ticker fiyatı likidasyon anını
                        # tam yakalamayabilir)
                        pnl = -SABIT_MARJIN_USDT
                    if tp_id:
                        try:
                            exchange.cancel_order(tp_id, sym)
                        except Exception:
                            pass
                    trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat, "pnl": pnl,
                                       "yon": yon, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                                       "not": sebep_etiket})
                    with state_lock:
                        trade_state.pop(sym, None)
                    durumu_diske_yaz()
                    with cooldown_lock:
                        son_kapanis_zamani[sym] = time.time()
                    cooldown_diske_yaz()
                    etiket_emoji = "🎯" if sebep_etiket == "tp_dolu" else "💥"
                    etiket_metin = "TP'ye ulaştı" if sebep_etiket == "tp_dolu" else "izole marjin likide oldu"
                    tg(f"{etiket_emoji} {sym} kapandı ({etiket_metin}) | PnL≈{pnl:+.2f}$")
            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


def baslangic_uzlastirma():
    try:
        gercek_pozlar = exchange.fetch_positions()
        gercek_semboller = {p["symbol"] for p in gercek_pozlar if safe(p.get("contracts")) > 0}
    except Exception as e:
        log.warning(f"[UZLASTIRMA] {e}")
        return
    with state_lock:
        state_semboller = set(trade_state.keys())
    sadece_diskte = state_semboller - gercek_semboller
    for sym in sadece_diskte:
        with state_lock:
            trade_state.pop(sym, None)
        with cooldown_lock:
            son_kapanis_zamani[sym] = time.time()
    if sadece_diskte:
        durumu_diske_yaz()
        cooldown_diske_yaz()
    sadece_borsada = gercek_semboller - state_semboller
    if sadece_borsada:
        tg(f"⚠️ UYARI: borsada açık ama state'te olmayan pozisyonlar: {sorted(sadece_borsada)}")


def tarama_loop():
    tg(f"🚀 SWING REVERSAL BOT v1.1 başladı\n"
       f"Mantık: dip/tepe + dönüş onayı (indikatörsüz, sadece fiyat)\n"
       f"LOOKBACK={LOOKBACK} mum (5m) | SL: swing±%{SL_BUFFER_PCT*100:.1f} (taban %{MIN_SL_PCT*100:.0f}/tavan %{MAX_SL_PCT*100:.0f}) | TP: {TP_R_ORANI}R\n"
       f"MAX_POS={MAX_POS} | Marjin: ${SABIT_MARJIN_USDT:.2f} sabit, {LEV}x\n"
       f"⚠️ Bu mantık hiç backtest edilmedi - sadece canlı veri toplanacak.")

    baslangic_uzlastirma()

    while True:
        try:
            with state_lock:
                bos_slot = MAX_POS - len(trade_state) - len(acilis_rezervasyonlari)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            adaylar = aday_havuzu()
            taranacaklar = []
            for sym in adaylar:
                with state_lock:
                    if sym in trade_state:
                        continue
                if cooldown_da_mi(sym):
                    continue
                taranacaklar.append(sym)

            if taranacaklar:
                with ThreadPoolExecutor(max_workers=TARAMA_PARALEL_WORKER) as havuz:
                    gelecekler = {havuz.submit(swing_sinyal, sym): sym for sym in taranacaklar}
                    for gelecek in as_completed(gelecekler):
                        sym = gelecekler[gelecek]
                        try:
                            sinyal = gelecek.result()
                        except Exception as e:
                            log.warning(f"[TARAMA] {sym}: {e}")
                            continue
                        if sinyal:
                            with state_lock:
                                if sym in trade_state:
                                    continue
                                bos_slot_simdi = MAX_POS - len(trade_state) - len(acilis_rezervasyonlari)
                            if bos_slot_simdi <= 0:
                                continue
                            yon_etiket = "dipten LONG" if sinyal["yon"] == "long" else "tepeden SHORT"
                            log.info(f"[SINYAL] {sym} {yon_etiket}")
                            try:
                                pozisyon_ac(sinyal)
                            except Exception as e:
                                log.error(f"[ACILIS_HATA] {sym}: {e}")
                                acilis_basarisiz_cooldown_uygula(sym)

            log.info(f"[NABIZ] tur tamam | havuz={len(adaylar)} | acik_pozisyon={MAX_POS-bos_slot}/{MAX_POS}")
            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("SWING REVERSAL BOT v1.1 BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    trade_log_yukle()
    bloke_diskten_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
