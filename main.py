#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
LIVE BOT v1.1 — Çoklu Zaman Dilimi Trend Uyumu (GERÇEK PARA)
12 Ağustos 2026

KULLANICI KARARI: paper_bot.py (v1.8) haftalarca sanal test edilecekti,
ama kullanıcı erken canlıya geçme kararı aldı - "paper bot'u gerçek
paraya çevir, aynı strateji, $1 marjin, max 3 pozisyon" talimatıyla.
Eski swing_bot (v6.3, swing dip/tepe stratejisi) SİLİNMEDİ, kendi
$3.5 bakiyesiyle ayrı çalışmaya devam ediyor - iki farklı strateji
paralel izleniyor.

STRATEJİ (paper_bot ile birebir aynı, SADECE gerçek emir açılıyor):
  1) 4H trend yönü belirlenir (20 periyot MA)
  2) 1H trend AYNI yönde olmalı - değilse sinyal yok
  3) 15m'de swing dip/tepe + dönüş onayı aranır
  4) Üçü uyumlu değilse marjinal kurulum açılmaz

⚠️ DÜRÜSTLÜK NOTU: Bu strateji paper modda hiç kapanan işlem
göstermeden canlıya alındı - istatistiksel doğrulama YOK. Kullanıcı
bu riski bilerek kabul etti.

Çıkış: SL (swing bazlı, geniş, hedef ~$0.90 kayıp) + İZ SÜREN TP
(1.0R aktifleşme, 0.5R geri çekilme).
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
log = logging.getLogger("LIVE_BOT")

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
    raise RuntimeError("MY_CHAT_ID ortam değişkeni eksik.")

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
    return chat_id == CHAT_ID


SLUGGISH_BASE = {"BTC", "ETH", "XRP", "ADA", "DOGE", "BNB", "TRX", "LINK", "LTC", "BCH"}

# ── GERÇEK işlem parametreleri ──
SABIT_MARJIN_USDT = float(os.getenv("SABIT_MARJIN_USDT", "1.0"))
# KULLANICI KARARI (12.08.2026): paper_bot'tan canlıya geçişte $1 sabit
# marjin - küçük, kontrollü risk ile gerçek veri toplamak için.
LEV = 10
NOTIONAL = SABIT_MARJIN_USDT * LEV
MAX_POS = int(os.getenv("MAX_POS", "3"))
# KULLANICI KARARI (12.08.2026): max 3 eşzamanlı pozisyon.

LOOKBACK_15M = 20
MA_PERIYOT = 20
SL_BUFFER_PCT = 0.015
MIN_SL_PCT = 0.05
MAX_SL_PCT = 0.09
TARGET_MAX_LOSS_USDT = float(os.getenv("TARGET_MAX_LOSS_USDT", "0.90"))
IZ_SURME_R_ORANI = 1.0
IZ_SURME_GERI_COKME_ORANI = 0.5
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
COOLDOWN_SAAT = 1.0
MAX_HOLD_SAAT = 24
KONTROL_ARALIGI_SN = 60
ADAY_HAVUZU_BUYUKLUGU = 80

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/live_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/live_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/live_log.json")
BLOKE_PATH = os.getenv("BLOKE_PATH", "/data/live_bloke.json")

trade_state = {}
state_lock = threading.Lock()
acilis_rezervasyonlari = {}
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()
bloke_coinler = set()
bloke_lock = threading.Lock()


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
            candles = candles[:-1]
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


def gercek_bakiye_al():
    try:
        bakiye = exchange.fetch_balance()
        usdt = bakiye.get("USDT", {})
        return safe(usdt.get("total", 0)) or safe(usdt.get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] {e}")
        return None


_market_cache = {"markets": None, "ts": 0}


def market_bilgisi_al():
    if _market_cache["markets"] is None or (time.time() - _market_cache["ts"]) > 3600:
        try:
            _market_cache["markets"] = exchange.load_markets()
            _market_cache["ts"] = time.time()
        except Exception as e:
            log.warning(f"[MARKET_BILGI] {e}")
    return _market_cache["markets"] or {}


def sembol_max_kaldirac(sym, istenen_lev):
    try:
        markets = market_bilgisi_al()
        m = markets.get(sym)
        if not m:
            return istenen_lev
        max_lev = (m.get("limits", {}) or {}).get("leverage", {}).get("max")
        if max_lev is None:
            return istenen_lev
        return min(istenen_lev, int(max_lev))
    except Exception:
        return istenen_lev


def aday_havuzu():
    # KRİTİK DÜZELTME (12.08.2026): tokenize hisse senetleri (AST SpaceMobile,
    # Lumentum Holdings vb. - RWA/gerçek dünya varlıkları) botun pozisyon
    # açtığı coin evrenine yanlışlıkla dahil olmuştu. Eski scalp_bot/swing_bot
    # bunları özellikle (isRwa=="YES" kontrolüyle) eliyordu, ama live_bot.py
    # basitleştirilirken bu filtre atlanmıştı. Hisseler borsa saatleri,
    # after-hours işlem gibi kripto'dan tamamen farklı dinamiklere sahip -
    # strateji bunlar üzerinde hiç test edilmedi. Şimdi geri eklendi.
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
        return []
    markets = market_bilgisi_al()
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE:
            continue
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
# ÇOKLU ZAMAN DİLİMİ UYUM SİNYALİ (paper_bot ile birebir aynı)
# ════════════════════════════════════════════
def trend_yonu(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma):
        return None
    return "yukselis" if fiyat > ma else "dusus"


def coktan_zaman_dilimi_sinyal(sym):
    df_4h = get_df(sym, "4h", MA_PERIYOT + 5)
    df_1h = get_df(sym, "1h", MA_PERIYOT + 5)
    df_15m = get_df(sym, "15m", LOOKBACK_15M + 5)

    yon_4h = trend_yonu(df_4h)
    yon_1h = trend_yonu(df_1h)
    if yon_4h is None or yon_1h is None or df_15m is None or len(df_15m) < LOOKBACK_15M + 2:
        return None

    if yon_4h != yon_1h:
        return None

    ust_trend = yon_4h

    pencere = df_15m.iloc[-(LOOKBACK_15M + 1):-1]
    son_mum = df_15m.iloc[-1]
    son_3_idx = pencere.index[-3:]

    if ust_trend == "yukselis":
        swing_low = pencere["low"].min()
        dip_idx = pencere["low"].idxmin()
        dip_yakin = dip_idx in son_3_idx
        yukari_kapandi = son_mum["close"] > son_mum["open"]
        if dip_yakin and yukari_kapandi and son_mum["close"] > swing_low:
            return {"symbol": sym, "entry": float(son_mum["close"]), "yon": "long",
                    "swing_nokta": float(swing_low), "4h": yon_4h, "1h": yon_1h}
    else:
        swing_high = pencere["high"].max()
        tepe_idx = pencere["high"].idxmax()
        tepe_yakin = tepe_idx in son_3_idx
        asagi_kapandi = son_mum["close"] < son_mum["open"]
        if tepe_yakin and asagi_kapandi and son_mum["close"] < swing_high:
            return {"symbol": sym, "entry": float(son_mum["close"]), "yon": "short",
                    "swing_nokta": float(swing_high), "4h": yon_4h, "1h": yon_1h}
    return None


# ════════════════════════════════════════════
# GERÇEK POZİSYON AÇMA/KAPATMA
# ════════════════════════════════════════════
def acilis_basarisiz_cooldown_uygula(sym):
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()


def gercek_pozisyon_ac(sinyal):
    sym = sinyal["symbol"]

    if coin_bloke_mi(sym):
        log.info(f"[COIN_BLOKE] {sym} engelli, açılış atlanıyor")
        return

    with state_lock:
        if sym in trade_state or sym in acilis_rezervasyonlari:
            return
        if len(trade_state) + len(acilis_rezervasyonlari) >= MAX_POS:
            return
        acilis_rezervasyonlari[sym] = True

    try:
        _gercek_pozisyon_ac_ic(sym, sinyal)
    finally:
        with state_lock:
            acilis_rezervasyonlari.pop(sym, None)


def _gercek_pozisyon_ac_ic(sym, sinyal):
    if cooldown_da_mi(sym):
        return

    bakiye = gercek_bakiye_al()
    if bakiye is None or bakiye <= 0:
        tg(f"⚠️ {sym} atlandı — bakiye alınamadı")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    entry_hedef = sinyal["entry"]
    yon = sinyal["yon"]
    swing_nokta = sinyal["swing_nokta"]

    if yon == "long":
        sl = swing_nokta * (1 - SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT, (entry_hedef - sl) / entry_hedef))
        sl = entry_hedef * (1 - sl_mesafe)
    else:
        sl = swing_nokta * (1 + SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT, (sl - entry_hedef) / entry_hedef))
        sl = entry_hedef * (1 + sl_mesafe)

    if sl_mesafe <= 0:
        acilis_basarisiz_cooldown_uygula(sym)
        return

    LEV_KULLANILAN = sembol_max_kaldirac(sym, LEV)
    notional = SABIT_MARJIN_USDT * LEV_KULLANILAN
    amount = notional / entry_hedef

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
    entry = entry_hedef
    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
        if gercek_pos and safe(gercek_pos.get("entryPrice")) > 0:
            entry = safe(gercek_pos.get("entryPrice"))
            sl = entry * (1 - sl_mesafe) if yon == "long" else entry * (1 + sl_mesafe)
    except Exception as e:
        log.warning(f"[GERCEK_POZ] {sym}: {e}")

    r_risk = abs(entry - sl)
    kapatma_yonu = "sell" if yon == "long" else "buy"

    sl_emir_id = None
    sl_fiyat = float(exchange.price_to_precision(sym, sl))
    for deneme in range(3):
        try:
            sl_emri = exchange.create_order(sym, "market", kapatma_yonu, qty, None,
                                             {"reduceOnly": True, "stopLossPrice": sl_fiyat})
            sl_emir_id = sl_emri.get("id")
            if sl_emir_id:
                break
        except Exception as e:
            log.warning(f"[SL] {sym} deneme {deneme+1}/3: {e}")
        time.sleep(0.5)

    if not sl_emir_id:
        tg(f"🚨 {sym} SL yerleştirilemedi, güvenlik amaçlı kapatılıyor.")
        try:
            exchange.create_market_order(sym, kapatma_yonu, qty, params={"reduceOnly": True})
        except Exception:
            pass
        acilis_basarisiz_cooldown_uygula(sym)
        return

    with state_lock:
        trade_state[sym] = {
            "entry": entry, "sl": sl, "sl_emir_id": sl_emir_id, "yon": yon, "qty": qty,
            "r_risk": r_risk, "acilis_zamani": time.time(), "en_iyi_kar": None, "iz_aktif": False,
            "4h": sinyal["4h"], "1h": sinyal["1h"], "notional": notional,
        }
    durumu_diske_yaz()

    risk_dolar = r_risk * qty
    iz_esik = risk_dolar * IZ_SURME_R_ORANI
    gc_esik = risk_dolar * IZ_SURME_GERI_COKME_ORANI
    tg(f"📈 GERÇEK POZİSYON: {sym} {yon.upper()}\n"
       f"Giriş≈{entry:.6f} | SL:{sl_fiyat:.6f} (%{sl_mesafe*100:.1f})\n"
       f"4H:{sinyal['4h']} | 1H:{sinyal['1h']} (uyumlu)\n"
       f"TP: İZ SÜREN — ${iz_esik:.2f} kârda aktifleşir (1.0R), en iyi kârdan "
       f"${gc_esik:.2f} geri çekilirse kapanır (0.5R)\n"
       f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Marjin: ${SABIT_MARJIN_USDT:.2f}")


def gercek_pozisyon_kapat(sym, sebep="manuel"):
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
                _kapanis_kaydet_gercek_veriyle(sym, durum, sebep)
            return True, "kapatildi"

        qty = safe(gercek_pos.get("contracts"))
        entry_fiyat = safe(gercek_pos.get("entryPrice"))
        pozisyon_yonu = gercek_pos.get("side", "long")
        kapama_yon = "sell" if pozisyon_yonu == "long" else "buy"

        if durum and durum.get("sl_emir_id"):
            try:
                exchange.cancel_order(durum["sl_emir_id"], sym)
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
                           "not": sebep, "4h": (durum or {}).get("4h"), "1h": (durum or {}).get("1h"),
                           "iz_surme_aktifti": (durum or {}).get("iz_aktif", False),
                           "en_iyi_kar": (durum or {}).get("en_iyi_kar")})
        with state_lock:
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        with cooldown_lock:
            son_kapanis_zamani[sym] = time.time()
        cooldown_diske_yaz()
        tg(f"{'🟢' if pnl>=0 else '🔴'} GERÇEK kapandı: {sym} [{sebep}] PnL≈{pnl:+.2f}$")
        return True, f"✅ {sym} kapatıldı | PnL≈{pnl:+.2f}$"
    except Exception as e:
        return False, f"⚠️ {sym} kapatma hatası: {e}"


def _kapanis_kaydet_gercek_veriyle(sym, durum, sebep):
    """Pozisyon borsada bizden önce kapanmış (SL tetiklenmiş vb.) - gerçek
    çıkış fiyatını borsanın işlem geçmişinden çekiyoruz, hiçbir zaman
    tahmin/varsayım yapmıyoruz."""
    entry = durum["entry"]
    qty = durum.get("qty", 0)
    yon = durum.get("yon", "long")
    cikis_fiyat = None
    sl_id = durum.get("sl_emir_id")
    if sl_id:
        try:
            detay = exchange.fetch_order(sl_id, sym)
            if detay.get("status") in ("closed", "filled"):
                dolum = safe(detay.get("average")) or safe(detay.get("price"))
                if dolum > 0:
                    cikis_fiyat = dolum
        except Exception as e:
            log.warning(f"[SL_KONTROL] {sym}: {e}")
    if not cikis_fiyat:
        try:
            son_islemler = exchange.fetch_my_trades(sym, limit=10)
            kapanis_zamani_ms = durum["acilis_zamani"] * 1000
            adaylar = [t for t in son_islemler if t.get("timestamp", 0) > kapanis_zamani_ms]
            if adaylar:
                son_islem = max(adaylar, key=lambda t: t.get("timestamp", 0))
                dolum = safe(son_islem.get("price"))
                if dolum > 0:
                    cikis_fiyat = dolum
        except Exception as e:
            log.warning(f"[ISLEM_GECMISI] {sym}: {e}")
    if not cikis_fiyat:
        try:
            t = exchange.fetch_ticker(sym)
            cikis_fiyat = safe(t["last"])
        except Exception:
            cikis_fiyat = entry

    pnl = (cikis_fiyat - entry) * qty if yon == "long" else (entry - cikis_fiyat) * qty
    trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat, "pnl": pnl,
                       "yon": yon, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                       "not": sebep, "4h": durum.get("4h"), "1h": durum.get("1h"),
                       "iz_surme_aktifti": durum.get("iz_aktif", False), "en_iyi_kar": durum.get("en_iyi_kar")})
    tg(f"{'🟢' if pnl>=0 else '🔴'} GERÇEK kapandı: {sym} [{sebep}] PnL≈{pnl:+.2f}$ (borsada önceden kapanmış)")


# ════════════════════════════════════════════
# PANEL (paper_bot v1.8 ile birebir aynı tasarım, gerçek veriyle)
# ════════════════════════════════════════════
def acik_pozisyonlar_gercek_pnl():
    with state_lock:
        durumlar = dict(trade_state)
    toplam = 0.0
    detaylar = []
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            entry = d["entry"]
            yon = d["yon"]
            poz_notional = d.get("notional", NOTIONAL)
            pnl_pct = (guncel - entry) / entry if yon == "long" else (entry - guncel) / entry
            anlik = pnl_pct * poz_notional
            toplam += anlik
            detaylar.append((sym, anlik))
        except Exception:
            continue
    return toplam, detaylar


def panel_ozet_metni():
    with log_lock:
        gecmis = list(trade_log)
    gerceklesmeyen_net, acik_detay = acik_pozisyonlar_gercek_pnl()
    with state_lock:
        acik_sayi = len(trade_state)
    gercek_bakiye = gercek_bakiye_al()
    bakiye_metni = f"{gercek_bakiye:,.2f}$" if gercek_bakiye is not None else "alınamadı"

    satirlar = [
        "💵 LIVE BOT — CANLI ÖZET",
        "(GERÇEK PARA)",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💼 Bakiye (borsa): {bakiye_metni}",
    ]
    if acik_sayi > 0:
        gc_emoji = "🟢" if gerceklesmeyen_net >= 0 else "🔴"
        satirlar.append(f"{gc_emoji} Açık pozisyonlarda (gerçekleşmemiş): {gerceklesmeyen_net:+.2f}$")
    satirlar.append("━━━━━━━━━━━━━━━━━━━━\n")

    if gecmis:
        toplam = len(gecmis)
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        net = sum(t["pnl"] for t in gecmis)
        wr = len(kazanan) / toplam * 100
        satirlar.append("📊 İstatistik")
        satirlar.append(f"  Toplam işlem: {toplam}  |  Kazanma: %{wr:.1f}")
        satirlar.append(f"  Net PnL (gerçekleşen): {net:+.2f}$")
        satirlar.append(f"  Ortalama işlem: {net/toplam:+.3f}$\n")
        satirlar.append("📋 Son 5 işlem:")
        for t in list(reversed(gecmis))[:5]:
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            sebep = t.get("not", "")
            satirlar.append(f"  {emoji} {t['symbol'].split('/')[0]:<8} {t['pnl']:+.2f}$  ({sebep})")
    else:
        satirlar.append("Henüz kapanan işlem yok.")

    satirlar.append(f"\n📈 Açık pozisyon: {acik_sayi}/{MAX_POS}")
    if acik_detay:
        for sym, anlik in acik_detay:
            e = "🟢" if anlik >= 0 else "🔴"
            satirlar.append(f"  {e} {sym.split('/')[0]:<8} {anlik:+.2f}$")
    return "\n".join(satirlar)


def panel_ayarlar_metni():
    return ("⚙️ LIVE BOT AYARLARI\n\n"
            "Sürüm: v1.0 (paper_bot v1.8'den gerçek paraya geçirildi - "
            "aynı strateji, aynı panel, artık gerçek emir açıyor)\n\n"
            "💰 BU BOT GERÇEK PARA KULLANIYOR.\n\n"
            "Strateji: Çoklu zaman dilimi trend uyumu\n"
            "  1) 4H trend yönü belirlenir (20 periyot MA)\n"
            "  2) 1H trend AYNI yönde olmalı - değilse sinyal yok\n"
            "  3) 15m'de swing dip/tepe + dönüş onayı aranır\n"
            "  4) Üçü uyumlu değilse marjinal kurulum açılmaz\n\n"
            f"Kaldıraç: {LEV}x | Marjin: sabit ${SABIT_MARJIN_USDT:.2f}\n"
            f"MAX_POS: {MAX_POS}\n"
            f"SL: swing bazlı, taban %{MIN_SL_PCT*100:.0f} / tavan %{MAX_SL_PCT*100:.0f}\n"
            f"TP: İZ SÜREN — {IZ_SURME_R_ORANI:.1f}R'de aktifleşir, "
            f"{IZ_SURME_GERI_COKME_ORANI:.1f}R geri çekilirse kapanır\n"
            f"Coin cooldown: {COOLDOWN_SAAT} saat | Max tutma: {MAX_HOLD_SAAT} saat\n"
            f"Tarama aralığı: {KONTROL_ARALIGI_SN}sn | Aday havuzu: {ADAY_HAVUZU_BUYUKLUGU} coin\n\n"
            "⚠️ Bu strateji paper modda hiç kapanan işlem göstermeden "
            "canlıya alındı - istatistiksel doğrulama yok, kullanıcı kararıyla.")


def panel_gecmis_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "📜 Henüz kapanan işlem yok."
    satirlar = ["📜 SON 15 İŞLEM\n"]
    for t in list(reversed(gecmis))[:15]:
        emoji = "🟢" if t["pnl"] >= 0 else "🔴"
        sebep = {"sl": "SL", "iz_suren_tp": "iz süren TP", "max_hold_timeout": "max süre"}.get(t.get("not"), t.get("not", "?"))
        iz_bilgi = ""
        if t.get("iz_surme_aktifti"):
            en_iyi = t.get("en_iyi_kar")
            if en_iyi is not None:
                iz_bilgi = f" | en iyi:{en_iyi:+.2f}$"
        satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} {t['yon'].upper()} {t['pnl']:+.2f}$ "
                         f"[{sebep}]{iz_bilgi}\n   {t['zaman']} | 4H:{t.get('4h','?')}/1H:{t.get('1h','?')}")
    return "\n".join(satirlar)


def panel_analiz_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "🔬 ANALİZ\n\nHenüz kapanan işlem yok."
    satirlar = ["🔬 ANALİZ\n"]

    satirlar.append("📊 Yöne göre:")
    for yon in ["long", "short"]:
        alt = [t for t in gecmis if t.get("yon") == yon]
        if not alt:
            continue
        kazanan = [t for t in alt if t["pnl"] > 0]
        net = sum(t["pnl"] for t in alt)
        satirlar.append(f"  {yon.upper()}: {len(alt)} işlem, %{len(kazanan)/len(alt)*100:.0f} kazanma, net {net:+.2f}$")

    satirlar.append("\n🚪 Kapanış sebebine göre:")
    for sebep in sorted(set(t.get("not", "?") for t in gecmis)):
        alt = [t for t in gecmis if t.get("not") == sebep]
        net = sum(t["pnl"] for t in alt)
        satirlar.append(f"  {sebep}: {len(alt)} işlem, net {net:+.2f}$")

    coin_pnl = {}
    for t in gecmis:
        sym = t["symbol"].split("/")[0]
        coin_pnl[sym] = coin_pnl.get(sym, 0) + t["pnl"]
    siralanmis = sorted(coin_pnl.items(), key=lambda x: x[1], reverse=True)
    kazandiranlar = [x for x in siralanmis if x[1] > 0][:3]
    kaybettirenler = [x for x in siralanmis if x[1] < 0][-3:][::-1]
    if kazandiranlar:
        satirlar.append("\n🏆 En kazandıran coinler:")
        for sym, pnl in kazandiranlar:
            satirlar.append(f"  {sym}: {pnl:+.2f}$")
    if kaybettirenler:
        satirlar.append("💀 En kaybettiren coinler:")
        for sym, pnl in kaybettirenler:
            satirlar.append(f"  {sym}: {pnl:+.2f}$")
    return "\n".join(satirlar)


def panel_risk_metni():
    with state_lock:
        durumlar = dict(trade_state)
    satirlar = ["📉 AÇIK POZİSYON DETAYI\n"]
    if not durumlar:
        satirlar.append("Açık pozisyon yok.")
        return "\n".join(satirlar)
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            yon = d["yon"]
            entry = d["entry"]
            pnl_pct = (guncel - entry) / entry * 100 if yon == "long" else (entry - guncel) / entry * 100
            anlik_kar = pnl_pct / 100 * d.get("notional", NOTIONAL)
            iz_durum = "🔒 aktif" if d.get("iz_aktif") else "🔓 pasif"
            en_iyi = d.get("en_iyi_kar")
            en_iyi_metin = f", en iyi: {en_iyi:+.2f}$" if en_iyi is not None else ""
            sure_dk = (time.time() - d["acilis_zamani"]) / 60
            satirlar.append(f"{sym} {yon.upper()} (4H:{d.get('4h')}/1H:{d.get('1h')})\n"
                             f"  Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                             f"  Anlık PnL: {anlik_kar:+.2f}$ | SL:{d['sl']:.6f}\n"
                             f"  İz sürme: {iz_durum}{en_iyi_metin}\n"
                             f"  Açık süre: {sure_dk:.0f} dk")
        except Exception:
            satirlar.append(f"{sym} (fiyat alınamadı)")
    return "\n".join(satirlar)


def ana_menu_klavye():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("📊 Özet", callback_data="panel_ozet"),
        telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="panel_ayarlar"),
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📜 Geçmiş", callback_data="panel_gecmis"),
        telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="panel_analiz"),
    )
    markup.row(telebot.types.InlineKeyboardButton("📉 Açık Pozisyon Detayı", callback_data="panel_risk"))
    markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="panel_ana"))
    return markup


def geri_butonu():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
    return markup


if bot:
    @bot.message_handler(commands=["panel"])
    def panel_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        veri = call.data
        try:
            if veri == "panel_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye())
            elif veri == "panel_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_ayarlar":
                bot.edit_message_text(panel_ayarlar_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_gecmis":
                bot.edit_message_text(panel_gecmis_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_analiz":
                bot.edit_message_text(panel_analiz_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_risk":
                bot.edit_message_text(panel_risk_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            bot.answer_callback_query(call.id)
        except Exception as e:
            if "message is not modified" not in str(e):
                log.warning(f"[PANEL_BUTON] {e}")
            try: bot.answer_callback_query(call.id, "Tamam")
            except Exception: pass

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_risk_metni())

    @bot.message_handler(commands=["ozet"])
    def ozet_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni())

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
        basari, mesaj = gercek_pozisyon_kapat(hedef)
        bot.send_message(msg.chat.id, mesaj)

    @bot.message_handler(commands=["blokla"])
    def blokla_komutu(msg):
        if not yetkili_mi(msg):
            return
        parca = msg.text.replace("/blokla", "", 1).strip().upper()
        if not parca:
            bot.send_message(msg.chat.id, "Kullanım: /blokla COIN_ADI")
            return
        with bloke_lock:
            bloke_coinler.add(parca)
        bloke_diske_yaz()
        bot.send_message(msg.chat.id, f"🚫 {parca} engellendi.")

    @bot.message_handler(commands=["blokkaldir"])
    def blokkaldir_komutu(msg):
        if not yetkili_mi(msg):
            return
        parca = msg.text.replace("/blokkaldir", "", 1).strip().upper()
        if not parca:
            bot.send_message(msg.chat.id, "Kullanım: /blokkaldir COIN_ADI")
            return
        with bloke_lock:
            vardi = parca in bloke_coinler
            bloke_coinler.discard(parca)
        bloke_diske_yaz()
        bot.send_message(msg.chat.id, f"✅ {parca} engeli kaldırıldı." if vardi else f"ℹ️ {parca} zaten engelli değildi.")

    @bot.message_handler(commands=["sifirlagecmis"])
    def sifirlagecmis_komutu(msg):
        if not yetkili_mi(msg):
            return
        global trade_log
        with log_lock:
            trade_log = []
        atomik_yaz(TRADE_LOG_PATH, [])
        bot.send_message(msg.chat.id, "🗑️ İşlem geçmişi sıfırlandı.")

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
            dosya.name = f"live_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
            bot.send_document(msg.chat.id, dosya, caption=f"📦 {len(veri)} işlem")
        except Exception as e:
            bot.send_message(msg.chat.id, f"⚠️ Hata: {e}")


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
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


def manage_loop():
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            for sym in semboller:
                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue
                try:
                    t = exchange.fetch_ticker(sym)
                    guncel = safe(t["last"])
                except Exception:
                    continue
                if guncel <= 0:
                    continue

                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    gercek_pozisyon_kapat(sym, "max_hold_timeout")
                    continue

                yon = durum["yon"]
                sl_vuruldu = (guncel <= durum["sl"]) if yon == "long" else (guncel >= durum["sl"])
                if sl_vuruldu:
                    gercek_pozisyon_kapat(sym, "sl")
                    continue

                entry = durum["entry"]
                r_risk = durum["r_risk"]
                poz_notional = durum.get("notional", NOTIONAL)
                anlik_kar = (guncel - entry) / entry * poz_notional if yon == "long" else (entry - guncel) / entry * poz_notional
                risk_usdt = (r_risk / entry) * poz_notional
                iz_esik = risk_usdt * IZ_SURME_R_ORANI
                gc_esik = risk_usdt * IZ_SURME_GERI_COKME_ORANI

                en_iyi = None
                if anlik_kar >= iz_esik or durum["iz_aktif"]:
                    with state_lock:
                        if sym in trade_state:
                            trade_state[sym]["iz_aktif"] = True
                            en_iyi = trade_state[sym]["en_iyi_kar"]
                            if en_iyi is None or anlik_kar > en_iyi:
                                trade_state[sym]["en_iyi_kar"] = anlik_kar
                                en_iyi = anlik_kar
                    if en_iyi is not None and anlik_kar <= en_iyi - gc_esik:
                        gercek_pozisyon_kapat(sym, "iz_suren_tp")

                # borsada pozisyon hâlâ var mı diye ara sıra doğrula (SL borsada
                # bizden önce tetiklenmiş olabilir)
                try:
                    pozlar = exchange.fetch_positions([sym])
                    gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
                    if not gercek_pos:
                        with state_lock:
                            durum2 = trade_state.pop(sym, None)
                        durumu_diske_yaz()
                        with cooldown_lock:
                            son_kapanis_zamani[sym] = time.time()
                        cooldown_diske_yaz()
                        if durum2:
                            _kapanis_kaydet_gercek_veriyle(sym, durum2, "sl_borsada_onceden")
                except Exception as e:
                    log.warning(f"[MANAGE_DOGRULA] {sym}: {e}")
            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


def tarama_loop():
    tg(f"🚀 LIVE BOT v1.1 başladı — GERÇEK PARA (4H+1H+15m uyumu)\n"
       f"MAX_POS={MAX_POS} | Marjin: ${SABIT_MARJIN_USDT:.2f} sabit, {LEV}x\n"
       f"SL taban %{MIN_SL_PCT*100:.0f}, tavan %{MAX_SL_PCT*100:.0f} | "
       f"TP: iz süren, {IZ_SURME_R_ORANI}R aktifleşme, {IZ_SURME_GERI_COKME_ORANI}R geri çekilme\n\n"
       f"📱 /panel yaz — tam menüyü görürsün.")

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

            bulunan = 0
            if taranacaklar:
                with ThreadPoolExecutor(max_workers=4) as havuz:
                    gelecekler = {havuz.submit(coktan_zaman_dilimi_sinyal, sym): sym for sym in taranacaklar}
                    for gelecek in as_completed(gelecekler):
                        sym = gelecekler[gelecek]
                        try:
                            sinyal = gelecek.result()
                        except Exception as e:
                            log.warning(f"[TARAMA] {sym}: {e}")
                            continue
                        if sinyal:
                            with state_lock:
                                if sym in trade_state or len(trade_state) + len(acilis_rezervasyonlari) >= MAX_POS:
                                    continue
                            gercek_pozisyon_ac(sinyal)
                            bulunan += 1

            log.info(f"[NABIZ] tur tamam | havuz={len(adaylar)} | bulunan={bulunan} | acik={MAX_POS-bos_slot}/{MAX_POS}")
            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("LIVE BOT v1.1 BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    bloke_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
