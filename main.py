#!/usr/bin/env python3
"""
FUTURESKRIPTO KANAL SİNYAL ANALİZİ — GEÇMİŞE DÖNÜK ÖRÜNTÜ ARAMA
🔖 VERSİYON: v1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Amaç: Kanalın DAHA ÖNCE gönderdiği sinyalleri (Telegram mesaj geçmişinden)
çekip, her birinin GÖNDERİLDİĞİ ANDAKİ teknik durumu (trend, RSI, hacim,
son fiyat hareketi) neydi diye geriye dönük hesaplar. Amaç: kanalın
"gizli" mantığında tekrar eden bir teknik örüntü var mı görmek.

BU BİR BACKTEST DEĞİL — sadece tanımlayıcı bir analiz. Sinyal başarılı
mı başarısız mı olduğunu da hesaplayıp, "başarılı sinyallerin ortak
özelliği neydi" diye karşılaştırabiliriz.

ÇALIŞTIRMA: pip install telethon ccxt pandas --break-system-packages
            python3 futureskripto_analiz.py
Gerekli ortam değişkenleri: TG_API_ID, TG_API_HASH, STRING_SESSION (ya
da TG_SESSION) — signal_copy_bot ile AYNI kimlik bilgileri kullanılabilir.
"""

import os
import re
import time
import asyncio
import ccxt
import pandas as pd
from datetime import datetime, timezone
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_STRING_SESSION = os.getenv("STRING_SESSION", "") or os.getenv("TG_SESSION", "")
KANAL = os.getenv("KANAL_USERNAME", "FuturesKripto")
KAC_MESAJ = 300  # geriye kaç mesaj taransın (sinyal olmayanlar da dahil, o yüzden yüksek tutuyoruz)

if not TG_API_ID or not TG_API_HASH or not TG_STRING_SESSION:
    raise RuntimeError("TG_API_ID / TG_API_HASH / STRING_SESSION eksik.")

exchange = ccxt.bitget({"options": {"defaultType": "swap"}, "enableRateLimit": True})


# ════════════════════════════════════════════
# SİNYAL AYRIŞTIRMA (signal_copy_bot ile AYNI mantık)
# ════════════════════════════════════════════
def sinyal_ayristir(metin):
    sembol_m = re.search(r"#(\w+?)USDT", metin, re.IGNORECASE)
    yon_m = re.search(r"\b(LONG|SHORT)\b", metin, re.IGNORECASE)
    giris_m = re.search(r"Giri[şs].*?Fiyat[ıi]?\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    stop_m = re.search(r"Stop\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    tp_liste = re.findall(r"TP\d+\s*:?\s*([\d.]+)", metin, re.IGNORECASE)

    if not (sembol_m and yon_m and giris_m and stop_m):
        return None

    return {
        "symbol_base": sembol_m.group(1).upper(),
        "symbol": f"{sembol_m.group(1).upper()}/USDT:USDT",
        "direction": "long" if yon_m.group(1).upper() == "LONG" else "short",
        "entry": float(giris_m.group(1)),
        "sl": float(stop_m.group(1)),
        "tp_liste": [float(x) for x in tp_liste],
    }


# ════════════════════════════════════════════
# TEKNİK BAĞLAM HESAPLAMA (sinyal anındaki durum)
# ════════════════════════════════════════════
def calc_rsi(closes, period=14):
    diffs = closes.diff()
    gains = diffs.clip(lower=0).rolling(period).mean()
    losses = (-diffs.clip(upper=0)).rolling(period).mean()
    rs = gains / losses.replace(0, 0.0001)
    return 100 - 100 / (1 + rs)


def teknik_baglam_hesapla(symbol, sinyal_zamani_ms):
    """
    Sinyal anındaki (ondan hemen ÖNCEKİ, bakış-öne hatası olmasın diye)
    4h/1h trend durumu, RSI, hacim oranını hesaplar.
    """
    sonuc = {"veri_var": False}
    try:
        for tf, anahtar in [("4h", "4h"), ("1h", "1h"), ("15m", "15m")]:
            since = sinyal_zamani_ms - (200 * 4 * 60 * 60 * 1000)  # bolca geçmiş veri
            mumlar = exchange.fetch_ohlcv(symbol, tf, since=since, limit=200)
            if not mumlar or len(mumlar) < 20:
                return sonuc
            df = pd.DataFrame(mumlar, columns=["t", "o", "h", "l", "c", "v"])
            df = df[df["t"] <= sinyal_zamani_ms].reset_index(drop=True)  # sadece sinyal ÖNCESİ
            if len(df) < 20:
                return sonuc

            son_kapanis = df["c"].iloc[-1]
            onceki_yuksek = df["h"].iloc[-21:-1].max()
            onceki_dusuk = df["l"].iloc[-21:-1].min()
            rsi = calc_rsi(df["c"]).iloc[-1]
            hacim_ort = df["v"].iloc[-21:-1].mean()
            hacim_simdi = df["v"].iloc[-1]

            sonuc[f"{anahtar}_trend"] = "yukselis" if df["h"].iloc[-1] > df["h"].iloc[-2] else (
                "dusus" if df["l"].iloc[-1] < df["l"].iloc[-2] else "yatay")
            sonuc[f"{anahtar}_rsi"] = round(rsi, 1)
            sonuc[f"{anahtar}_yuksek20_yakinlik_pct"] = round((son_kapanis - onceki_yuksek) / onceki_yuksek * 100, 2)
            sonuc[f"{anahtar}_dusuk20_yakinlik_pct"] = round((son_kapanis - onceki_dusuk) / onceki_dusuk * 100, 2)
            sonuc[f"{anahtar}_hacim_orani"] = round(hacim_simdi / hacim_ort, 2) if hacim_ort > 0 else None

        sonuc["veri_var"] = True
    except Exception as e:
        sonuc["hata"] = str(e)
    return sonuc


# ════════════════════════════════════════════
# SONUÇ DEĞERLENDİRME (sinyal sonrasında TP'ye mi SL'e mi gitti)
# ════════════════════════════════════════════
def sinyal_sonucu_hesapla(symbol, direction, entry, sl, tp_liste, sinyal_zamani_ms):
    try:
        mumlar = exchange.fetch_ohlcv(symbol, "15m", since=sinyal_zamani_ms, limit=500)
        if not mumlar:
            return "veri_yok"
        df = pd.DataFrame(mumlar, columns=["t", "o", "h", "l", "c", "v"])
        ilk_tp = tp_liste[0] if tp_liste else None

        for _, row in df.iterrows():
            sl_vuruldu = (row["l"] <= sl) if direction == "long" else (row["h"] >= sl)
            tp_vuruldu = ilk_tp and ((row["h"] >= ilk_tp) if direction == "long" else (row["l"] <= ilk_tp))
            if sl_vuruldu and tp_vuruldu:
                return "belirsiz(ayni_mum)"
            if sl_vuruldu:
                return "SL"
            if tp_vuruldu:
                return "TP_basladi"
        return "sonuclanmadi(veri_bitti)"
    except Exception as e:
        return f"hata:{e}"


# ════════════════════════════════════════════
# ANA
# ════════════════════════════════════════════
def main():
    print("🔖 VERSİYON: v1\n")
    print(f"═══ {KANAL} KANALI — GEÇMİŞ SİNYAL ANALİZİ ═══\n")

    client = TelegramClient(StringSession(TG_STRING_SESSION), TG_API_ID, TG_API_HASH)
    client.start()

    sinyaller = []
    print(f"Son {KAC_MESAJ} mesaj taranıyor...")
    for mesaj in client.iter_messages(KANAL, limit=KAC_MESAJ):
        if not mesaj.text:
            continue
        sinyal = sinyal_ayristir(mesaj.text)
        if sinyal:
            sinyal["zaman_ms"] = int(mesaj.date.timestamp() * 1000)
            sinyal["zaman_str"] = mesaj.date.strftime("%Y-%m-%d %H:%M")
            sinyaller.append(sinyal)

    print(f"\nToplam {len(sinyaller)} sinyal bulundu. Her biri için teknik bağlam + sonuç hesaplanıyor...\n")

    satirlar = []
    for i, s in enumerate(sinyaller):
        print(f"[{i+1}/{len(sinyaller)}] {s['symbol']} {s['direction'].upper()} ({s['zaman_str']})")
        baglam = teknik_baglam_hesapla(s["symbol"], s["zaman_ms"])
        sonuc = sinyal_sonucu_hesapla(s["symbol"], s["direction"], s["entry"], s["sl"], s["tp_liste"], s["zaman_ms"])
        satir = {**s, **baglam, "sonuc": sonuc}
        satirlar.append(satir)
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(satirlar)
    df.to_csv("futureskripto_analiz.csv", index=False)
    print("\n'futureskripto_analiz.csv' dosyasına kaydedildi.")

    print("\n" + "═" * 50)
    print("ÖZET (TP_basladi vs SL karşılaştırması):")
    for grup, alt_df in df.groupby("sonuc"):
        print(f"\n--- {grup} ({len(alt_df)} sinyal) ---")
        for kolon in ["4h_trend", "1h_trend", "4h_rsi", "1h_rsi", "4h_hacim_orani"]:
            if kolon in alt_df.columns:
                print(f"  {kolon}: {alt_df[kolon].value_counts().to_dict() if alt_df[kolon].dtype == object else round(alt_df[kolon].mean(), 2)}")
    print("═" * 50)


if __name__ == "__main__":
    main()
