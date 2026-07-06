#!/usr/bin/env python3
"""
FUTURESKRIPTO KANAL SİNYAL ANALİZİ — GEÇMİŞE DÖNÜK ÖRÜNTÜ ARAMA
🔖 VERSİYON: v2 (Binance yedek veri kaynağı eklendi — Bitget'te olmayan coinler)
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
exchange_binance = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True})


def veri_cek_yedekli(symbol, timeframe, since=None, limit=200):
    """
    Önce Bitget'ten dener; sembol orada yoksa (kanal Binance'e göre sinyal
    veriyor, bazı coinler Bitget'te işlem görmüyor) Binance'ten dener.
    """
    try:
        return exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit), "bitget"
    except Exception:
        pass
    try:
        return exchange_binance.fetch_ohlcv(symbol, timeframe, since=since, limit=limit), "binance"
    except Exception as e:
        return None, f"hata:{e}"


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
    return 100 - 100 / (1 + rs)


def calc_macd(closes, hizli=12, yavas=26, sinyal=9):
    ema_hizli = closes.ewm(span=hizli, adjust=False).mean()
    ema_yavas = closes.ewm(span=yavas, adjust=False).mean()
    macd = ema_hizli - ema_yavas
    sinyal_hattii = macd.ewm(span=sinyal, adjust=False).mean()
    histogram = macd - sinyal_hattii
    return macd, sinyal_hattii, histogram


def calc_bollinger_yuzde_b(closes, period=20, std_mult=2.0):
    orta = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    ust = orta + std_mult * std
    alt = orta - std_mult * std
    genislik = (ust - alt).replace(0, 0.0001)
    yuzde_b = (closes - alt) / genislik  # 0=alt banda yapışık, 1=üst banda yapışık, 0.5=orta
    return yuzde_b


def calc_atr_percentile(df, period=14, pencere=100):
    high, low, close = df["h"], df["l"], df["c"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    if len(atr) < pencere + 5:
        return None
    simdiki = atr.iloc[-1]
    gecmis = atr.iloc[-pencere - 1:-1]
    return (gecmis < simdiki).mean() * 100  # yüzde kaçı şu andan düşük (yüksek=oynak, düşük=sıkışık)


def teknik_baglam_hesapla(symbol, sinyal_zamani_ms):
    """
    Sinyal anındaki (ondan hemen ÖNCEKİ, bakış-öne hatası olmasın diye)
    4h/1h trend durumu, RSI, hacim oranını hesaplar. Ayrıca MACD, Bollinger
    %B, EMA9/21 kesişimi, ATR percentile (sıkışma/genişleme) de hesaplar —
    kanalın "gizli" mantığını daha geniş bir gösterge setiyle arıyoruz.
    """
    sonuc = {"veri_var": False}
    try:
        for tf, anahtar in [("4h", "4h"), ("1h", "1h"), ("15m", "15m")]:
            since = sinyal_zamani_ms - (200 * 4 * 60 * 60 * 1000)  # bolca geçmiş veri
            mumlar, kaynak = veri_cek_yedekli(symbol, tf, since=since, limit=200)
            if not mumlar or len(mumlar) < 20:
                sonuc["hata"] = f"{symbol} icin veri bulunamadi (bitget+binance denendi)"
                return sonuc
            sonuc["veri_kaynagi"] = kaynak
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

            # ── YENİ: "zaten pump yapmış mı" testi — kullanıcının orijinal
            # gözlemini doğrudan sayısal olarak ölçüyoruz ──
            if len(df) >= 6:
                fiyat_5mum_once = df["c"].iloc[-6]
                sonuc[f"{anahtar}_son5mum_degisim_pct"] = round((son_kapanis - fiyat_5mum_once) / fiyat_5mum_once * 100, 2)
            if len(df) >= 21:
                fiyat_20mum_once = df["c"].iloc[-21]
                sonuc[f"{anahtar}_son20mum_degisim_pct"] = round((son_kapanis - fiyat_20mum_once) / fiyat_20mum_once * 100, 2)

            # ── YENİ GÖSTERGELER ──
            if len(df) >= 35:
                macd, macd_sinyal, macd_hist = calc_macd(df["c"])
                sonuc[f"{anahtar}_macd_pozitif"] = bool(macd.iloc[-1] > macd_sinyal.iloc[-1])
                sonuc[f"{anahtar}_macd_hist"] = round(float(macd_hist.iloc[-1]), 6)

            if len(df) >= 21:
                yuzde_b = calc_bollinger_yuzde_b(df["c"])
                sonuc[f"{anahtar}_boll_yuzdeB"] = round(float(yuzde_b.iloc[-1]), 3) if not pd.isna(yuzde_b.iloc[-1]) else None

                ema9 = df["c"].ewm(span=9, adjust=False).mean()
                ema21 = df["c"].ewm(span=21, adjust=False).mean()
                sonuc[f"{anahtar}_ema9_ustunde_ema21"] = bool(ema9.iloc[-1] > ema21.iloc[-1])

            if tf in ("4h", "1h"):
                atr_pct = calc_atr_percentile(df)
                if atr_pct is not None:
                    sonuc[f"{anahtar}_atr_percentile"] = round(atr_pct, 1)

        sonuc["veri_var"] = True
    except Exception as e:
        sonuc["hata"] = str(e)
    return sonuc


# ════════════════════════════════════════════
# SONUÇ DEĞERLENDİRME (sinyal sonrasında TP'ye mi SL'e mi gitti)
# ════════════════════════════════════════════
def sinyal_sonucu_hesapla(symbol, direction, entry, sl, tp_liste, sinyal_zamani_ms):
    """
    YENİ: Artık sadece "SL mi TP'ye mi gitti" değil, ULAŞILAN EN UZAK TP
    SEVİYESİNİ de (TP1, TP2, ... TP6) hesaplıyor — kanalın gerçekten kaç
    numaralı TP'ye kadar gittiğini net görmek için (kullanıcının gözlemini
    doğrulamak/çürütmek üzere).
    """
    try:
        mumlar, kaynak = veri_cek_yedekli(symbol, "15m", since=sinyal_zamani_ms, limit=500)
        if not mumlar:
            return f"veri_yok ({kaynak})", 0
        df = pd.DataFrame(mumlar, columns=["t", "o", "h", "l", "c", "v"])

        en_uzak_tp = 0  # kaç numaralı TP'ye ulaşıldı (0 = hiçbiri)
        sl_vuruldu_mu = False

        for _, row in df.iterrows():
            sl_vuruldu = (row["l"] <= sl) if direction == "long" else (row["h"] >= sl)

            for idx, tp in enumerate(tp_liste):
                tp_vuruldu = (row["h"] >= tp) if direction == "long" else (row["l"] <= tp)
                if tp_vuruldu and (idx + 1) > en_uzak_tp:
                    en_uzak_tp = idx + 1

            if sl_vuruldu:
                sl_vuruldu_mu = True
                break

        if sl_vuruldu_mu and en_uzak_tp == 0:
            return "SL(hic_TP_yok)", 0
        elif sl_vuruldu_mu:
            return f"SL(TP{en_uzak_tp}_sonrasi)", en_uzak_tp
        elif en_uzak_tp == len(tp_liste) and len(tp_liste) > 0:
            return "TUM_TPler_TAMAMLANDI", en_uzak_tp
        elif en_uzak_tp > 0:
            return f"TP{en_uzak_tp}_ye_kadar(veri_bitti)", en_uzak_tp
        else:
            return "sonuclanmadi(veri_bitti)", 0
    except Exception as e:
        return f"hata:{e}", 0


# ════════════════════════════════════════════
# ANA
# ════════════════════════════════════════════
def main():
    print("🔖 VERSİYON: v5 (pump-degisim testi + karar agaci ayni calistirmada birlesti - tek dosya, tek calistirma)\n")
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
        sonuc, en_uzak_tp = sinyal_sonucu_hesapla(s["symbol"], s["direction"], s["entry"], s["sl"], s["tp_liste"], s["zaman_ms"])
        satir = {**s, **baglam, "sonuc": sonuc, "en_uzak_tp": en_uzak_tp}
        satirlar.append(satir)
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(satirlar)
    df.to_csv("futureskripto_analiz.csv", index=False)
    print("\n'futureskripto_analiz.csv' dosyasına kaydedildi.")

    print("\n" + "═" * 50)
    print("EN UZAK ULAŞILAN TP DAĞILIMI (kullanıcının 'çoğu TP6'ya ulaşıyor' iddiasını test ediyor):")
    dagilim = df["en_uzak_tp"].value_counts().sort_index()
    toplam = len(df)
    for tp_no, sayi in dagilim.items():
        etiket = "Hiç TP yok" if tp_no == 0 else f"TP{tp_no}'e kadar ulaştı"
        print(f"  {etiket}: {sayi} sinyal (%{sayi/toplam*100:.1f})")
    print(f"\nOrtalama ulaşılan TP seviyesi: {df['en_uzak_tp'].mean():.2f}")
    print(f"TP6'ya ulaşanların oranı: %{(df['en_uzak_tp']>=6).sum()/toplam*100:.1f}")

    print("\n" + "═" * 50)
    print("ÖZET (sonuç kategorisine göre teknik bağlam):")
    for grup, alt_df in df.groupby("sonuc"):
        print(f"\n--- {grup} ({len(alt_df)} sinyal) ---")
        for kolon in ["4h_trend", "1h_trend", "4h_rsi", "1h_rsi", "4h_hacim_orani",
                      "4h_macd_pozitif", "1h_macd_pozitif", "4h_boll_yuzdeB", "1h_boll_yuzdeB",
                      "4h_ema9_ustunde_ema21", "1h_ema9_ustunde_ema21",
                      "4h_atr_percentile", "1h_atr_percentile",
                      "4h_son5mum_degisim_pct", "1h_son5mum_degisim_pct",
                      "4h_son20mum_degisim_pct", "1h_son20mum_degisim_pct"]:
            if kolon in alt_df.columns:
                print(f"  {kolon}: {alt_df[kolon].value_counts().to_dict() if alt_df[kolon].dtype == object else round(alt_df[kolon].mean(), 2)}")
    print("═" * 50)

    # ── EK ADIM: karar ağacıyla otomatik örüntü arama (AYNI ÇALIŞTIRMADA,
    # CSV'ye ihtiyaç duymadan — Railway'de dosyalar kalıcı olmadığı için
    # ayrı bir script/deploy gerektirmesin diye buraya birleştirildi) ──
    print("\n\n" + "═" * 50)
    print("KARAR AĞACI İLE OTOMATİK ÖRÜNTÜ ARAMA")
    print("═" * 50)
    try:
        from sklearn.tree import DecisionTreeClassifier, export_text

        df["hedef_tp6_ulasti"] = (df["en_uzak_tp"] >= 6).astype(int)
        sayisal_kolonlar = [c for c in df.columns if any(
            anahtar in c for anahtar in ["_rsi", "_hacim_orani", "_boll_yuzdeB", "_atr_percentile",
                                           "_macd_hist", "_degisim_pct", "_yakinlik_pct"]
        )]
        print(f"Kullanılan göstergeler ({len(sayisal_kolonlar)}): {sayisal_kolonlar}\n")

        X = df[sayisal_kolonlar].copy()
        for kolon in X.columns:
            X[kolon] = pd.to_numeric(X[kolon], errors="coerce")
        X = X.fillna(X.median(numeric_only=True))
        y = df["hedef_tp6_ulasti"]

        if len(X) >= 10 and not X.isna().all().all():
            agac = DecisionTreeClassifier(max_depth=3, min_samples_leaf=3, random_state=42)
            agac.fit(X, y)

            print(export_text(agac, feature_names=list(X.columns)))

            print("\nGÖSTERGE ÖNEM SIRALAMASI:")
            onem = sorted(zip(X.columns, agac.feature_importances_), key=lambda x: -x[1])
            for isim, deger in onem:
                if deger > 0:
                    print(f"  {isim}: {deger:.3f}")

            dogruluk = agac.score(X, y)
            print(f"\n⚠️ Eğitim verisi üzerinde doğruluk: %{dogruluk*100:.1f}")
            print("(GERÇEK bir doğrulama değil — aynı veriyle eğitilip test edildi, sadece")
            print(" 'ağaç bir kural bulabildi mi' sorusuna cevap. Küçük örneklemle ezberleme")
            print(" riski yüksek, çıkan kuralı temkinli değerlendir.)")
        else:
            print("Yeterli sayısal veri yok, karar ağacı analizi atlandı.")
    except ImportError:
        print("⚠️ scikit-learn kurulu değil — bu adımı atlıyoruz.")
        print("İstersen requirements.txt'e 'scikit-learn' ekleyip tekrar dene.")


if __name__ == "__main__":
    main()
