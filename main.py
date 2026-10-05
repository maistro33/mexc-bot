#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
LIVE BOT v7.2 — MANUEL ONAY PANELİ + WEB PANELİ + OTOMATİK BİLDİRİM + ANİ HAREKET ALARMI (30.09.2026, kullanıcı kararı: otomatik
strateji kendi başına işlem açmıyor; /tara ile aday bulunur, kullanıcı
onaylarsa "Aç" butonuyla açılır — bkz. v6.0/v6.1/v6.2 notları aşağıda). Eski
otomatik strateji kodu (1D+4H+1H uyum / günün en çok yükseleni, LONG-only)
OTOMATIK_GIRIS_AKTIF=true yapılırsa hâlâ çalışır, varsayılan KAPALI.

v7.2 (05.10.2026): KART ÜSTÜNDEN AYAR. Her sinyal kartının altında kaldıraç (3x/5x/10x), marjin ($3/$5/$10) ve marjin modu (İzole/Cross) düğmeleri var;
seçili olan ✅ ile gösterilir, kart seçime göre yeniden çizilir (pozisyon büyüklüğü, uyarılar dahil). "Aç/Gir"e basınca bot seçilen ayarı uygular:
önce marjin modunu, sonra kaldıracı ayarlar, sonra emri gönderir. Varsayılan: İzole, 5x, $5 (MARJIN_MODU, LEV_SECENEKLERI, MARJIN_SECENEKLERI ile değişir).
Pozisyon dolunca borsadaki GERÇEK marjin modu, kaldıraç ve likidasyon okunur; beklenenden farklıysa uyarı verir. Cross seçilirse kartta uyarı çıkar.

v7.1 (05.10.2026): HATA DÜZELTMESİ: kaldıraç 5x istenmesine rağmen pozisyon 10x açıldı (kaldıraç ayarı hata verince sessizce eski değerde
kalıyordu; Bitget izole+hedge modunda holdSide gerekebiliyor). (1) set_leverage artık holdSide ile, olmazsa parametresiz deneniyor; başarısızsa emir
mesajında uyarı çıkıyor. (2) Pozisyon dolunca borsadaki GERÇEK kaldıraç ve likidasyon fiyatı okunup "AÇILDI" mesajında gösteriliyor; beklenenden farklıysa
ya da likidasyon SL'ye çok yakın/öndeyse 🚨/⚠️ uyarısı veriliyor. (Otomatik düzeltme yok, sadece uyarı: marjin ekleme/kaldıraç değiştirmeyi sen yaparsın.)

v7.0 (05.10.2026): GERÇEKÇİ BACKTEST'E GÖRE İKİ DEĞİŞİKLİK. (1) Kaldıraç ortam değişkeni oldu (KALDIRAC), varsayılan 5x (önce sabit 10x).
(2) Ani hareket kartlarında SL en fazla %4 (ANI_HAREKET_SL_TAVAN_PCT), TP/R-R buna göre. Gerekçe (187 coin/45 gün/5 dk mum, komisyon+kayma+
likidasyon dahil): kartın doğal SL'i (medyan %12) 10x'te işlemlerin %33'ünü likide etti (-$0.66/işlem); SL<=%4 ile pozitif (+$0.19, 10x) ve
5x'te kötü stop kaymasında (%1) hesabı patlatmıyor. KENAR İNCE: en iyi senaryoda marjin üzerinden 45 günde ~%4; stop kayması %0.5'e çıkarsa sıfıra yakın.
OTOMATİK İŞLEM AÇMA ÖNERİLMEZ (OTOMATIK_GIRIS_AKTIF kapalı kalmalı; o eski stratejiyi çalıştırır, ani hareket sinyallerini değil).
Karttaki geçmiş istatistiği bu backtest'le güncellendi.

v6.9 (04.10.2026): GARANTİ VERİLEMEZ. v6.8'deki KISA hacim 2.0x şartı GERİ ALINDI (baştan simülasyonda fayda göstermedi; v6.8'de
yazılan %85 rakamı hatalı dilimlemeden çıkmıştı). Kartlardaki geçmiş istatistiği düzeltildi: KISA %81 kazanma (n=305), kaybedenlerde ort. -%9.
Her karta "GARANTİ YOK" uyarısı kaldı. 4H/1H RSI ve EMA şartları denendi, kazanma oranını artırmadı (eklenmedi).

v6.7 (04.10.2026): ANİ HAREKET sinyal eşikleri backtest'e göre sıkılaştırıldı (zayıf sinyalleri elemek için):
KISA için son 30 dk düşüşü %3 yerine %5, UZUN için 3 günlük çöküş %25 yerine %40.
Eski 'otomatik bildirim' (4S+1S) varsayılan olarak KAPATILDI: sadece ani hareket alarmı gelir. Ayrıntı: ANI_HAREKET_ESIK_KISA_PCT
ve ANI_HAREKET_UZUN_MIN_3GUN_PCT ayarlarının yanındaki not. Bedeli: sinyal sayısı belirgin azalır (özellikle UZUN).

v6.6 (04.10.2026): (1) HATA DÜZELTMESİ: /tara komutu yanlışlıkla ani_hareket_kart_metni fonksiyonuna
bağlanmıştı (dekoratör yanlış yerdeydi); Telegram'dan elle yazılan /tara hata veriyordu, panel
butonu çalışıyordu. Dekoratör kaldırıldı. (2) Kartlara ve emir mesajına LİKİDASYON UYARISI eklendi:
SL mesafesi tahmini likidasyondan uzaksa bildirir. Sinyal kuralına DOKUNULMADI: 187 coin/50 gün
backtest'te (iz sürmeli çıkış) mevcut kural kısa n=687 kazanma %73.5 ort +%1.01, 4H EMA/RSI veya
72s tepe-dip filtreleri sonucu iyileştirmedi (bkz. sohbet), bu yüzden eklenmedi.

v4.0 (17.09.2026, kullanıcı isteğiyle): Canlı botta trend-uyum
sinyalinin, kararsız/yatay piyasa koşullarında zayıf sinyalleri
eleyemediği gözlemlendi (panel_analiz: max_hold_timeout %44 kazanma
net -2.34$, sl %33 kazanma net -3.79$ - hizli_tp ve kismi_kar_alma
ise hâlâ %100 kazanmaya devam ediyordu, yani sorun ÇIKIŞTA değil
GİRİŞ SİNYALİNİN SEÇİCİLİĞİNDEYDİ). Önce "trend gücü eşiğini
yükselt" denendi, ama 136 coin/~51 gün gerçek veride BÜYÜK ÖLÇEKLİ
backtest edildiğinde net kârı ARTIRMADIĞI, tam tersine AZALTTIĞI
görüldü (guc=%2.0: net +1211$ / guc=%3.5: net +557$, kazanma oranı
hemen hemen aynı kalırken sadece işlem sayısı düşüyordu).
Bunun yerine, paper bot'ta ayrıca doğrulanmış "günün en çok yükseleni"
(momentum) stratejisi (2377 işlem, %5/%5 TP/SL ile net +5940$, üst
%10 dilimde) canlı botun GİRİŞ SİNYALİ seçeneği olarak eklendi -
ÇIKIŞ MEKANİĞİ VE POZİSYON BOYUTLANDIRMA DEĞİŞTİRİLMEDİ (paper
bot'un ham $100 sabit pozisyonu DEĞİL, canlı botun kendi bileşik
büyüme + kısmi kâr alma + breakeven sistemi korundu - orantısız risk
almamak için).
STRATEJI_MODU="otomatik" (varsayılan): BTC'nin kendi rejimine
(TEMKINLI_MOD_AKTIF sinyaline) göre kendisi seçer - BTC zayıfken
"yukselen" moduna, güçlüyken "trend" moduna geçer.
⚠️ DÜRÜSTLÜK NOTU: Bu OTOMATİK GEÇİŞİN KENDİSİ ayrı ayrı büyük
ölçekte test EDİLMEDİ - sadece iki stratejinin her biri bağımsız
olarak doğrulandı. Geçiş mantığı makul bir hipotez ama kanıtlanmamış,
yakından izlenmesi gerekiyor.
14 Ağustos 2026 (v2.0) → 21 Ağustos 2026 (v2.1) → 22 Ağustos 2026 (v2.2) → 14 Eylül 2026 (v3.6 → v3.7 → v3.8 → v3.9)

v3.9 (14.09.2026, kullanıcı kararıyla — "BTC'den bağımsız pump yapan coinleri kaçırmayalım" isteğiyle bulundu):
  v3.8'deki "BTC düşerse yeni pozisyonu TAMAMEN durdur" kararı geri
  alındı - orijinal kodun kendi geçmişinde bu tam olarak denenip terk
  edilmişti ("coin'leri tamamen engellemek yanlış çıkmıştı"). Yeni
  yaklaşım: MAX_POS yine yarıya iner (v3.7 davranışı), AMA o dönemde
  girecek coin için trend gücü eşiği YÜKSELTİLİR (MIN_4H_TREND_GUCU_PCT_TEMKINLI=%4.0, normalde %2.0). Böylece BTC
  zayıfken sadece BTC'den GERÇEKTEN bağımsız, güçlü hareket eden
  coinler işleme girebilir - zayıf/sınırda sinyaller elenir. "Hiçbir
  şey yapma" (v3.7) ile "her şeyi durdur" (v3.8) arasında orta yol.

v3.8 (14.09.2026, kullanıcı kararıyla — "piyasa dönünce bot bocalıyor,
kârlar eriyor" gözlemiyle bulundu):
  TEMKİNLİ MOD artık BTC'nin 1D+4H trendi düşüşe döndüğünde YENİ pozisyon
  açmayı TAMAMEN durduruyor (önceden sadece MAX_POS yarıya iniyordu).
  Açık pozisyonlara DOKUNULMAZ - onlar kendi SL/TP/kısmi kâr alma
  mantığıyla yönetilmeye devam eder.

  DEĞERLENDİRİLİP REDDEDİLEN ALTERNATİF: "trend dönünce pozisyonu
  tersine çevir / SHORT'a geç". Bu, kodun kendi geçmişinde zaten
  denenmiş ve başarısız olmuş bir yaklaşımdı - SHORT özelliği
  10.09.2026'da eklenip ilk gerçek işlemde (SLX) "short squeeze" ile
  kayıp verip 11.09.2026'da kapatılmıştı. Trend dönüş sinyali (1D+4H+1H
  üçünün de dönmesi) doğası gereği GEÇ gelir - bu noktada pozisyonu
  tersine çevirmek, geçici bir sıçramaya (whipsaw) yakalanıp hem eski
  hem yeni yönde kayıp verme riskini artırır. Bu yüzden tek yönlü,
  daha temkinli bir önlem seçildi: yeni risk eklemeyi durdur, var olan
  pozisyonlara müdahale etme.

v3.7 (14.09.2026, kullanıcı kararıyla — "KASA BÜYÜMESİ" isteğiyle bulundu):
  1) KISMİ KÂR ALMA + BREAKEVEN: pozisyon %1.5'e ulaşınca miktarın
     yarısı kapatılır (o kâr garanti altına alınır), kalan kısmın SL'i
     girişe (breakeven + komisyon payı) çekilir. Amaç: "%5 hedefe
     ulaşmadan pozisyon geri dönüp o ana kadarki kâr buharlaşıyor"
     sorununu azaltmak.
  2) KÜÇÜK BAKİYEDE MARJİN TABANI DÜZELTMESİ: hesapla_marjin() artık
     min(MARJIN_TABAN_USDT, bakiye/MAX_POS) kullanıyor. Önceden küçük
     bakiyelerde (örn. 4.26$) sabit $2 taban, bakiyenin ~%47'sini tek
     işleme kilitleyip MAX_POS'un çeşitlendirme amacını fiilen boşa
     çıkarıyordu. Artık bakiye küçükken pozisyon boyutu da küçülüyor,
     bakiye büyüyünce (MARJIN_TABAN_USDT*MAX_POS'u geçince) normal
     tabana otomatik dönüyor.
  ⚠️ Her iki değişiklik de henüz canlıda test edilmedi.

v3.6 (14.09.2026, kullanıcı kararıyla — GERÇEK VERİ ANALİZİNE DAYALI):
  161 gerçek işlemlik canlı log analiz edildi. Sonuç:
    - hizli_tp (19 işlem): net +18.17$, %100 kazanma → giriş YÖNÜ doğru,
      ama bu YALNIZCA işlemlerin %12'sinde gerçekleşiyor.
    - max_hold_timeout (128 işlem, toplamın %80'i): net -7.11$, %44 kazanma
      → botun asıl kanaması burada. 1D+4H+1H uyumu tek başına yeterince
      ayrıştırıcı değil, çok sık oluşan düşük-bilgi-değerli bir durum.
    - sl + sl_borsada_onceden (14 işlem): net -13.84$, %0 kazanma → nadir
      ama sert kayıplar (genelde önceden aşırı pompalanmış coinlerde).
  Net: -2.78$ / 161 işlem.

  Bu bulguya dayanarak İKİ YENİ FİLTRE eklendi (giriş sinyalini daha
  seçici hale getirmek için, backtest'e değil canlı veriye dayalı):

  1) HACİM TEYİDİ: sinyal anındaki 15m mumun hacmi, önceki 20 mumun
     ortalamasının en az HACIM_TEYIT_KATSAYI katı olmalı. Amaç: "sessiz"
     (gerçek alım ilgisi olmayan) fiyat hareketlerini elemek - bunlar
     genelde ne hedefe ulaşıyor ne net ters dönüyor, sadece max_hold'a
     kadar sürünüp hafif eksi kapanıyor (log'daki 128 işlemin çoğu bu).

  2) PUMP FİLTRESİ (coin zaten aşırı pompalanmışsa LONG girişi reddet):
     24 saatlik değişim PUMP_FILTRE_ESIK_PCT üzerindeyse giriş yapılmaz.
     Log'daki en sert SL kayıplarının (CATI, PROS, ZEN, DOOD, BR, PIEVERSE)
     ortak paterni: coin zaten güçlü yükselmişken girilmiş, hemen ardından
     sert geri çekilme SL'i tetiklemiş - klasik "tepede giriş" riski.

  Her iki eşik de (HACIM_TEYIT_KATSAYI=1.5, PUMP_FILTRE_ESIK_PCT=15.0)
  ilk tahmin değerleridir - birkaç günlük canlı veriyle (panel_analiz)
  gözden geçirilmesi gerekir.

  API YÜKÜNÜ ARTIRMAMAK İÇİN: pump filtresi ayrı fetch_ticker çağrısı
  yapmıyor, aday_havuzu()'nun zaten çektiği fetch_tickers() sonucunu
  kısa süreliğine (TICKER_CACHE_SN) önbellekleyip oradan okuyor.

v2.1 (21.08.2026, kullanıcı kararıyla):
  1) TEMKİNLİ MOD — BTC'nin kendi 1D+4H trendi ikisi de düşüşe dönerse
     MAX_POS geçici olarak yarıya iner (açık pozisyonlar etkilenmez).
  2) İZLEME LİSTESİ AJANI — paper_bot_v2'de test edildi, genel taramanın
     (en hareketli 80 coin) kaçırabileceği "sessiz" (büyük hareket
     olmadan 1D+4H'ye uyan) coinleri ayrı bir listede (max 10) izler.

v2.2 (22.08.2026, kullanıcı kararıyla): "bazı coinler kâra geçiyor sonra
birden düşüyor, sürekli kâr alan hızlı çıkan bot olsun, saatlerce
beklenmesin" isteğiyle:
  - İz sürme aktifleşme eşiği 1.0R'den 0.4R'ye indirildi
  - Geri çekilme payı 0.3R'den 0.15R'ye indirildi
  - Max tutma süresi 24 saatten 8 saate indirildi
  Bedeli: büyük/yavaş gelişen trend hareketlerinde daha erken çıkıp
  potansiyel ek kârı kaçırma riski artar - kullanıcı bu takası bilerek
  kabul etti (kârı erken koru > büyük hareketi tam yakala).

KULLANICI KARARI: Eski live_bot (v1.7, 4H+1H+15m, LONG+SHORT) durduruldu.
Onun yerine, paper_bot_v2'de (sanal) test edilen ve daha güçlü çekirdek
performans gösteren strateji gerçek paraya alındı.

TREND DÖNÜŞ AJANI (hem eski live_bot'ta hem paper_bot_v2'de test edildi,
İKİSİNDE DE net zarar verdiği görüldü) - KULLANICI KARARIYLA VARSAYILAN
KAPALI. Kod silinmedi, TREND_AJANI_AKTIF=true ile tekrar açılabilir.

MANTIK:
  1) 1D trend YUKARI olmalı (20 periyot MA)
  2) 4H trend YUKARI olmalı
  3) 1H trend YUKARI olmalı
  4) Üçü uyumlu değilse sinyal YOK
  5) 15m'de swing dip + dönüş onayı → LONG (SADECE LONG)
  6) [v3.6 YENİ] Hacim teyidi: son mum hacmi ortalamanın üstünde olmalı
  7) [v3.6 YENİ] Pump filtresi: coin 24s'te aşırı pompalanmışsa reddet

Çıkış: SL (swing bazlı, taban %5) + SABİT %5 HEDEF (v3.0: iz sürme
KALDIRILDI, hedefe değer değmez hemen kapanır - "hızlı gir çık" modu).

⚠️ DÜRÜSTLÜK NOTU: v3.6'daki iki yeni filtre, 161 işlemlik GERÇEK canlı
veri analizine dayanıyor (backtest'e değil). Ama bu filtrelerin kendisi
henüz canlıda test edilmedi - etkilerini görmek için birkaç günlük yeni
veri toplanıp panel_analiz ile tekrar değerlendirilmesi gerekir.
════════════════════════════════════════════════════════
"""

import os
import time
import json
import uuid
from flask import Flask, request, jsonify, Response
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
log = logging.getLogger("LIVE_BOT_V2")

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
RISK_PCT_BAKIYE = float(os.getenv("RISK_PCT_BAKIYE", "0.06"))  # v5.7: 4 slotta toplam en kötü kaybı sınırlamak için
MARJIN_TABAN_USDT = float(os.getenv("MARJIN_TABAN_USDT", "1.0"))
MARJIN_TAVAN_USDT = float(os.getenv("MARJIN_TAVAN_USDT", "50.0"))
SABIT_MARJIN_USDT = float(os.getenv("SABIT_MARJIN_USDT", "2.0"))
# v7.0: kaldıraç artık ortam değişkeni (KALDIRAC), varsayılan 5x. Gerçekçi backtest (187 coin/45 gün, komisyon+kayma+likidasyon):
# 10x'te kartların geniş SL'i likidasyondan önce çalışmadığı için işlemlerin %33'ü likide oldu (-$0.66/işlem); 5x'te likidasyon
# mesafesi ~%14.7 olduğundan stop çalışabiliyor ve kötü stop kaymasında (%1) bile hesap patlamıyor. Coin'in izin verdiği
# maksimum kaldıraç bundan düşükse o kullanılır (sembol_max_kaldirac).
LEV = int(os.getenv("KALDIRAC", "5"))
NOTIONAL = SABIT_MARJIN_USDT * LEV  # sadece eski koddaki referanslar için tutuluyor
# v7.2: kart düğmelerindeki seçenekler ve varsayılan marjin modu (izole = kayıp marjinle sınırlı, cross = tüm bakiye ortak)
MARJIN_MODU = "cross" if os.getenv("MARJIN_MODU", "isolated").lower() in ("cross", "crossed") else "isolated"
LEV_SECENEKLERI = [int(x) for x in os.getenv("LEV_SECENEKLERI", "3,5,10").split(",") if x.strip()]
MARJIN_SECENEKLERI = [float(x) for x in os.getenv("MARJIN_SECENEKLERI", "3,5,10").split(",") if x.strip()]
MAX_POS = int(os.getenv("MAX_POS", "4"))  # v5.7: kullanıcı kararı (bakiye boşta kalmasın)

LOOKBACK_15M = 20
MA_PERIYOT = 20
SL_BUFFER_PCT = 0.015
MIN_SL_PCT = 0.05
TARGET_MAX_LOSS_USDT = float(os.getenv("TARGET_MAX_LOSS_USDT", "0.90"))
MAX_SL_PCT_TAVAN = TARGET_MAX_LOSS_USDT / (SABIT_MARJIN_USDT * 10)   # v7.0: eski otomatik stratejinin davranışı kaldıraçtan etkilenmesin diye 10x üzerinden sabit

# ════════════════════════════════════════════
# KULLANICI KARARI (01.09.2026): FIRSATÇI STRATEJİYE GEÇİŞ
# ════════════════════════════════════════════
GIRIS_MAX_DIP_MESAFE = float(os.getenv("GIRIS_MAX_DIP_MESAFE", "0.02"))
MIN_4H_TREND_GUCU_PCT = float(os.getenv("MIN_4H_TREND_GUCU_PCT", "2.0"))

# ════════════════════════════════════════════
# v4.0 YENİ: STRATEJİ MODU SEÇİMİ
# ════════════════════════════════════════════
# KULLANICI KARARI (17.09.2026, kullanıcı isteğiyle): Paper bot'ta
# 136 coin/~51 gün gerçek veride büyük ölçekli backtest edilen "günün
# en çok yükseleni" (momentum) stratejisi (2283 işlem, net +7254$,
# %80-95 eşik ve %4-7 TP/SL aralığında İSTİKRARLI pozitif), canlı botun
# GİRİŞ SİNYALİ olarak eklendi - ÇIKIŞ MEKANİĞİ VE POZİSYON
# BOYUTLANDIRMA DEĞİŞTİRİLMEDİ. Paper bot'un ham $100 sabit pozisyon +
# %6 TP/SL'i DOĞRUDAN KOPYALANMADI - bunun yerine canlı botun kendi
# kanıtlanmış risk yönetimi (bileşik büyüme pozisyon boyutu, kısmi kâr
# alma + breakeven, mevcut %5 TP/SL) korunarak sadece giriş mantığı
# değiştirildi. Gerekçe: paper bot'ta $60'lık tekil SL kayıpları
# görüldü (sabit $100 pozisyonun %6'sı) - bunu olduğu gibi ~$5-10'luk
# gerçek hesaba taşımak orantısız risk olurdu.
# STRATEJI_MODU="trend": eski 1D+4H+1H uyumu (v3.9 ve öncesi)
# STRATEJI_MODU="yukselen": günün en çok yükseleni + hacim teyidi
STRATEJI_MODU = os.getenv("STRATEJI_MODU", "yukselen")
YUKSELEN_UST_YUZDELIK = float(os.getenv("YUKSELEN_UST_YUZDELIK", "0.80"))  # v4.9: backtest'te doğrulanan üst %20
# v5.5: üst dilim eşiği negatifken aday vermeme kuralı (varsayılan KAPALI, bkz. yukselen_coin_havuzu)
YUKSELEN_NEGATIF_ESIK_ENGEL = os.getenv("YUKSELEN_NEGATIF_ESIK_ENGEL", "false").lower() == "true"

# v5.6 YENİ: GÜNLÜK ZARAR FRENİ - bugün (UTC) gerçekleşen zarar, gün başı bakiyenin
# GUNLUK_ZARAR_LIMIT_PCT'ini aşarsa YENİ işlem açılmaz (açık pozisyonlar yönetilmeye
# devam eder). Bir kâr iddiası değil, kötü bir günün hasarını sınırlar.
GUNLUK_ZARAR_FRENI_AKTIF = os.getenv("GUNLUK_ZARAR_FRENI_AKTIF", "true").lower() == "true"
GUNLUK_ZARAR_LIMIT_PCT = float(os.getenv("GUNLUK_ZARAR_LIMIT_PCT", "0.06"))
# v5.6 YENİ: sürtünme (kayma) kaydı - sinyal/tetik fiyatı ile gerçek dolum farkı
SURTUNME_PATH = os.getenv("LIVE_SURTUNME_PATH", "/data/live2_surtunme.json")

# v5.8 YENİ: KOVALAMA KORUMASI - anlık fiyat, sinyal mumunun kapanışından bu yüzdeden fazla
# PAHALIYSA (long için üstündeyse) girilmez; fiyat geri gelirse aynı 15dk penceresinde girilir.
# Örnek: ONDO sinyal kapanışı 0.5370, bot 0.5409'dan girdi (%0.73 pahalı). Zarar sınırlayıcıdır,
# kâr artışı vaat etmez; etkisi /surtunme verisiyle ölçülecek.
KOVALAMA_KORUMA_AKTIF = os.getenv("KOVALAMA_KORUMA_AKTIF", "true").lower() == "true"
KOVALAMA_MAX_PCT = float(os.getenv("KOVALAMA_MAX_PCT", "0.4"))
# v5.8 YENİ: AYNI MUMDAN SINIRLI GİRİŞ - tek bir 15dk mumundan (piyasa geneli sıçrama) en fazla bu
# kadar pozisyon açılır. ONDO ve JASMY aynı 12:00 mumundan çıkıp birlikte kaybetmişti. 0 = kapalı.
AYNI_MUM_MAX_GIRIS = int(os.getenv("AYNI_MUM_MAX_GIRIS", "2"))
# v5.9 YENİ: HİSSE/ETF/EMTİA (Bitget'te isRwa=YES) vadelileri varsayılan olarak DIŞLANIR.
# Gerekçe (28.09.2026, SOXS girişi + 36 günlük backtest): (a) bu enstrümanlarda "hacim 1.2x" şartı her
# ABD açılışında (13:30 UTC) kendiliğinden sağlanıyor - gerçek momentum değil saat etkisi; (b) 63 işlemde
# ort/işlem %-0.02 (kriptoda +%0.67) - ölçülebilir üstünlük yok (örnek küçük, kesin değil); (c) 3x kaldıraçlı
# ETF'ler ve piyasa açılış/kapanış boşlukları stop'u atlayabilir. True yapılırsa tekrar dahil edilir.
RWA_HISSE_DAHIL = os.getenv("RWA_HISSE_DAHIL", "false").lower() == "true"

# ════════════════════════════════════════════
# v6.0 YENİ (30.09.2026, kullanıcı kararı): MANUEL ONAY PANELİ.
# Otomatik strateji artık KENDİ BAŞINA işlem AÇMIYOR (OTOMATIK_GIRIS_AKTIF
# varsayılan false) - kullanıcı /tara ile aday listesi ister, her adayı
# 4S (ana filtre) + 1S (giriş zamanlaması) + 15dk (sadece güncel fiyat)
# ile gösterir, kullanıcı "Aç" butonuna basmadan hiçbir emir gitmez.
# Otomatik yönetim (mevcut pozisyonların SL/TP/iz sürme/günlük fren/
# stop teşhisi) DEĞİŞMEDİ, aynen çalışmaya devam ediyor.
OTOMATIK_GIRIS_AKTIF = os.getenv("OTOMATIK_GIRIS_AKTIF", "false").lower() == "true"
MANUEL_RSI_PERIYOT = int(os.getenv("MANUEL_RSI_PERIYOT", "14"))
MANUEL_SL_BUFFER_PCT = float(os.getenv("MANUEL_SL_BUFFER_PCT", "0.004"))
MANUEL_MIN_RR = float(os.getenv("MANUEL_MIN_RR", "1.3"))
MANUEL_MAKS_KART = int(os.getenv("MANUEL_MAKS_KART", "5"))
# v6.4 YENİ: OTOMATİK BİLDİRİM - bot arka planda düzenli tarar, temiz bir
# kurulum bulunca (kart + Aç/Düzenle/Geç butonlarıyla) Telegram'a HABER VERİR.
# Bu OTOMATİK İŞLEM AÇMA DEĞİL - hiçbir emir kullanıcı onayı olmadan gitmez,
# sadece taramayı elle yapma ihtiyacını azaltır.
# v6.7: varsayılan KAPALI. Kullanıcı sadece ani hareket alarmını istiyor; /bildirimkapat bellekte tutulduğu için
# her deploy'da (yeniden başlatmada) eski 4S+1S bildirimi geri açılıyordu. Açmak için /bildirimac ya da ortam değişkeni.
OTOMATIK_BILDIRIM_AKTIF = os.getenv("OTOMATIK_BILDIRIM_AKTIF", "false").lower() == "true"
OTOMATIK_BILDIRIM_ARALIK_SN = int(os.getenv("OTOMATIK_BILDIRIM_ARALIK_SN", str(30*60)))
OTOMATIK_BILDIRIM_COOLDOWN_SN = int(os.getenv("OTOMATIK_BILDIRIM_COOLDOWN_SN", str(2*3600)))

# v6.5 YENİ: ANİ DÖNÜŞ ALARMI - en çok yükselen/düşen ilk birkaç coin ayrıca
# izlenir; bunlardan biri KISA sürede ters yöne sert hareket ederse (zirve
# yapan coin aniden düşmeye başlarsa, dip yapan coin aniden sıçrarsa) haber
# verilir. Bu da OTOMATİK İŞLEM AÇMA DEĞİL - sadece "buna hemen bak" uyarısı.
ANI_HAREKET_AKTIF = os.getenv("ANI_HAREKET_AKTIF", "true").lower() == "true"
ANI_HAREKET_ARALIK_SN = int(os.getenv("ANI_HAREKET_ARALIK_SN", "90"))
# "Çok şişmiş/çok düşmüş" eşiği: son 3 günde en az bu kadar hareket etmiş olmalı
# (28.09.2026 backtest: 3 günde >=%25 hareket eden coinlerde, zamanlamayı beklemeden
# girmek bile tutarlı pozitif sonuç verdi - bkz. tukenme_testi.py). Bu yüzden önce
# 3 günlük şişkinlik filtrelenir, SONRA o adaylarda güçlü ters hareket aranır.
ANI_HAREKET_3GUN_ESIK_PCT = float(os.getenv("ANI_HAREKET_3GUN_ESIK_PCT", "25.0"))
# "Güçlü satış/alım başladı" penceresi ve eşiği (son X dakikada ters yöne bu kadar hareket)
ANI_HAREKET_PENCERE_DK = int(os.getenv("ANI_HAREKET_PENCERE_DK", "30"))
ANI_HAREKET_ESIK_PCT = float(os.getenv("ANI_HAREKET_ESIK_PCT", "3.0"))   # UZUN sinyal: son penceredeki yükseliş eşiği
# v6.7/v6.9 (187 coin/50 gün backtest, her eşik baştan simüle edildi, iz sürmeli çıkış, komisyon %0.12, kayma yok):
#  KISA (3g>=%25, hacim>=1.3x): 30dk eşiği -%3: n=682 kazanma %73 ort +%0.99 | -%4: n=446 %77 +%1.44 | -%5: n=305 %81 +%1.86
#        (ilk/son yarıda ikisi de pozitif). Eşik yükseldikçe kazanma oranı ve ortalama düzenli artıyor.
#  UZUN (30dk>=+%3): 3 günlük çöküş -%25: n=159 %74 +%0.96 (t=2.0) | -%35: n=69 %83 +%2.29 | -%40: n=40 %87.5 +%3.32 (örnek küçük).
ANI_HAREKET_ESIK_KISA_PCT = float(os.getenv("ANI_HAREKET_ESIK_KISA_PCT", "5.0"))
ANI_HAREKET_UZUN_MIN_3GUN_PCT = float(os.getenv("ANI_HAREKET_UZUN_MIN_3GUN_PCT", "40.0"))
# Hacim teyidi: pencere içindeki hacim, önceki ortalamanın en az bu katı olmalı
# (zayıf hacimli küçük dalgalanmaları elemek için)
ANI_HAREKET_HACIM_CARPANI = float(os.getenv("ANI_HAREKET_HACIM_CARPANI", "1.3"))
# v6.9: KISA için ayrı hacim şartı eklenmişti (v6.8: 2.0x), GERİ ALINDI: baştan simülasyonda 2.0x kazanma oranını
# artırmadı (30dk<=-%5: 1.3x -> n=305 %81.3 +%1.86; 2.0x -> n=203 %82.3 +%1.90) ve sinyal sayısını 1/3 azalttı.
# (v6.8'deki "%85" rakamı, sinyaller tekilleştirildikten SONRA dilimlenmekten doğan yanıltıcı bir sonuçtu.)
ANI_HAREKET_HACIM_CARPANI_KISA = float(os.getenv("ANI_HAREKET_HACIM_CARPANI_KISA", "1.3"))
# v7.0: ani hareket kartlarında SL en fazla bu yüzde (%) uzakta olur, TP ve R/R buna göre yeniden hesaplanır.
# Backtest (5x/10x, likidasyon dahil): kartın doğal SL'i (medyan %12) 10x'te zarar, SL<=%4 ile pozitif ve likidasyonsuz.
ANI_HAREKET_SL_TAVAN_PCT = float(os.getenv("ANI_HAREKET_SL_TAVAN_PCT", "4.0"))
ANI_HAREKET_TAKIP_SAYISI = int(os.getenv("ANI_HAREKET_TAKIP_SAYISI", "8"))
ANI_HAREKET_COOLDOWN_SN = int(os.getenv("ANI_HAREKET_COOLDOWN_SN", str(2*3600)))
MANUEL_LIMIT_TIMEOUT_SN = int(os.getenv("MANUEL_LIMIT_TIMEOUT_SN", str(6*3600)))
MANUEL_MARJIN_VARSAYILAN_USDT = float(os.getenv("MANUEL_MARJIN_VARSAYILAN_USDT", "5.0"))

# ════════════════════════════════════════════
# v6.2 YENİ: WEB PANELİ (Flask). Ayrı bir web arayüzü - Telegram'daki aynı
# verileri ve aksiyonları (durdur/başlat/tümünü kapat/manuel aç/kapat)
# tarayıcıdan sunar. ŞİFRE ZORUNLU (WEB_PANEL_SIFRE) - boşsa panel API'si
# hiçbir isteğe cevap vermez (güvenlik varsayılanı: kapalı sayılır).
WEB_PANEL_AKTIF = os.getenv("WEB_PANEL_AKTIF", "true").lower() == "true"
WEB_PANEL_SIFRE = os.getenv("WEB_PANEL_SIFRE", "")
WEB_PANEL_PORT = int(os.getenv("PORT", os.getenv("WEB_PANEL_PORT", "8080")))
YUKSELEN_HACIM_KATSAYI = float(os.getenv("YUKSELEN_HACIM_KATSAYI", "1.2"))
# v5.2 YENİ: mum gövde gücü eşiği - zayıf/kararsız mumları eler
YUKSELEN_MIN_GOVDE_ORANI = float(os.getenv("YUKSELEN_MIN_GOVDE_ORANI", "0.45"))
# v4.1 YENİ: "tam tepede alım" riskini azaltmak için zirveden mesafe filtresi
ZIRVE_LOOKBACK = int(os.getenv("ZIRVE_LOOKBACK", "20"))
ZIRVEDEN_MIN_MESAFE_PCT = float(os.getenv("ZIRVEDEN_MIN_MESAFE_PCT", "0.015"))

# v4.9 KRİTİK DÜZELTME (23.09.2026, güncel gerçek veriyle backtest edilip
# bulundu): v4.5-v4.8'deki SABİT DOLAR hedefi ($0.35), şu anki küçük
# pozisyon boyutunda (~$48 notional) sadece ~%0.7'lik bir fiyat hareketine
# denk geliyordu - bu, gerçek bir momentum sinyalinden çok PİYASA
# GÜRÜLTÜSÜ seviyesinde kalıyordu. Son 10 günlük gerçek veride büyük
# ölçekli backtest yapıldı: %2'nin altındaki her hedef NET ZARARLI
# çıktı (gürültüye yenik düşüyordu), %3 ve üstü NET KÂRLI çıktı. %3,
# "mümkün olduğunca hızlı ama hâlâ kârlı" noktayı temsil ediyor
# (ortalama ~2 saatte sonuçlanıyor, %5'in ~2.75 saatinden daha hızlı).
# ARTIK TEKRAR YÜZDESEL - SABİT DOLAR YERİNE - kullanılıyor, böylece
# bakiye büyüdükçe hem kazanç hem kayıp ORANTILI büyür (risk/ödül oranı
# sabit kalır, v4.8'deki dolar bazlı SL düzeltmesinin amacı da korunmuş
# olur, ama artık yüzdesel skalada).
YUKSELEN_HEDEF_PCT = float(os.getenv("YUKSELEN_HEDEF_PCT", "0.03"))
YUKSELEN_SL_PCT = float(os.getenv("YUKSELEN_SL_PCT", "0.03"))
# v5.0 YENİ: İZ SÜRME (trailing stop) - kullanıcı önerisiyle bulundu,
# güncel gerçek veride backtest edildi (üst %20 dilim, %3 hedef):
# iz sürme YOKKEN net +121$, VARKEN (aktivasyon %2.5, takip payı %0.5)
# net +519$ - 4 kattan fazla iyileşme. KISMI KÂR ALMADAN (v3.7-v4.4'te
# denenip yükselen modu için zararlı bulunmuştu) FARKI: kısmi kâr alma
# pozisyonun bir kısmını erken satıp kalanını breakeven'e sabitliyordu -
# bu, büyük hareketleri yakalama potansiyelini kesiyordu. İZ SÜRME İSE
# TAM POZİSYONU KORUYOR, sadece SL'i kârın gerisinden takip ettiriyor -
# fiyat devam ederse tam hedefe ulaşılabiliyor, dönerse kilitlenen kârla
# çıkılıyor. Sadece YUKSELEN modunda uygulanıyor.
YUKSELEN_TRAILING_AKTIF = os.getenv("YUKSELEN_TRAILING_AKTIF", "true").lower() == "true"
YUKSELEN_TRAILING_AKTIVASYON_PCT = float(os.getenv("YUKSELEN_TRAILING_AKTIVASYON_PCT", "0.025"))
YUKSELEN_TRAILING_PAYI_PCT = float(os.getenv("YUKSELEN_TRAILING_PAYI_PCT", "0.005"))
# v5.1 YENİ: TP tavanını kaldırma anahtarı - backtest'te tavan var/yok
# tamamen aynı sonucu verdiği için (iz sürme zaten %3'ten önce yakalıyordu),
# varsayılan olarak tavan KAPALI - büyük hareketler tam yakalanabilsin.
YUKSELEN_TP_TAVAN_AKTIF = os.getenv("YUKSELEN_TP_TAVAN_AKTIF", "false").lower() == "true"
# v4.7 YENİ: anlık (24s yerine son birkaç mum) volatilite eşiği
ANLIK_VOLATILITE_MUM = int(os.getenv("ANLIK_VOLATILITE_MUM", "2"))  # 2x15m = son 30 dk
ANLIK_VOLATILITE_MIN_PCT = float(os.getenv("ANLIK_VOLATILITE_MIN_PCT", "1.0"))

# ════════════════════════════════════════════
# v4.2 → v4.3 GÜNCELLEME: ERKEN GÜVENLİK ÇIKIŞI
# ════════════════════════════════════════════
# KULLANICI KARARI (22.09.2026, v4.2): IOTX (-1.07$) ve FLOCK (-1.02$)
# gibi büyük tekil kayıpları önlemek için eklenmişti - hiç kısmi kâr
# alma noktasına (%1.5) ulaşmadan doğrudan tam SL'e (%5) gitmişlerdi.
#
# KULLANICI KARARI (23.09.2026, v4.3, gerçek veri analiziyle GERİ
# ALINDI): 136 coin/~51 gün gerçek veride büyük ölçekli backtest
# yapıldığında, bu mekanizmanın YUKSELEN modu için net ZARARLI olduğu
# görüldü - koruma yokken net +7254$ olan sonuç, erken güvenlik
# çıkışı eklenince +1461$'a düşüyordu (kazanma oranı %48.2'den
# %23.9'a çöküyordu). Sebep: bu strateji zaten "biraz dalgalanıp
# sonra patlayan" işlemlere dayanıyor - erken çıkış bu potansiyeli
# daha oluşmadan kesiyor. Canlı veride de aynı patern doğrulandı
# (paper v2 korumalı: 31 işlem/%25.8 kazanma/+99$ vs orijinal
# korumasız: 98 işlem/%61.2 kazanma/+1508$).
# VARSAYILAN ARTIK KAPALI. Zirveden mesafe filtresi (giriş kalitesi)
# KORUNUYOR - o ayrı test edildi ve zararsız/faydalı çıktı. Sadece bu
# ÇIKIŞ mekanizması geri alındı. Sabit SL (%5) zaten kayıp tavanını
# koruyor - kontrolsüz büyüme riski yok, sadece bazen tam SL boyutunda
# (büyükçe) bir kayıp görülecek, bu kabul edilen bir maliyet.
ERKEN_GUVENLIK_CIKISI_AKTIF = os.getenv("ERKEN_GUVENLIK_CIKISI_AKTIF", "false").lower() == "true"
ERKEN_GUVENLIK_SURE_DK = float(os.getenv("ERKEN_GUVENLIK_SURE_DK", "40"))
ERKEN_GUVENLIK_MAX_ZARAR_PCT = float(os.getenv("ERKEN_GUVENLIK_MAX_ZARAR_PCT", "1.0"))
ERKEN_GUVENLIK_MIN_ILERLEME_PCT = float(os.getenv("ERKEN_GUVENLIK_MIN_ILERLEME_PCT", "0.3"))
# "otomatik": BTC rejimine göre kendisi seçer - BTC zayıfken (temkinli
# mod aktif) "yukselen" (günün en çok yükseleni) moduna, BTC güçlüyken
# "trend" (1D+4H+1H uyumu) moduna geçer. Mantık: BTC zayıfken genel
# piyasa trendine dayalı sinyaller daha az güvenilir olabilir (bugünkü
# gerçek veri gözlemiyle bulundu - trend_gücü eşiğini yükseltmek net
# kârı ARTIRMADI, azalttı), bunun yerine anlık momentumu takip eden
# bağımsız bir sinyale geçmek denendi.
# ⚠️ DÜRÜSTLÜK NOTU: Bu rejim-bazlı OTOMATİK GEÇİŞİN KENDİSİ ayrı ayrı
# büyük ölçekte test EDİLMEDİ - sadece iki stratejinin her biri
# bağımsız olarak (136 coin/~51 gün) doğrulandı. Geçiş mantığı makul
# bir hipotez ama kanıtlanmamış - yakından izlenmeli.
HIZLI_HEDEF_PCT = float(os.getenv("HIZLI_HEDEF_PCT", "0.05"))
SHORT_AKTIF = os.getenv("SHORT_AKTIF", "false").lower() == "true"
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
COOLDOWN_SAAT = 1.0
MAX_HOLD_SAAT = float(os.getenv("MAX_HOLD_SAAT", "8"))
KONTROL_ARALIGI_SN = 60
ADAY_HAVUZU_BUYUKLUGU = 80

# ════════════════════════════════════════════
# v3.6 YENİ: HACİM TEYİDİ + PUMP FİLTRESİ
# ════════════════════════════════════════════
# KULLANICI KARARI (14.09.2026, 161 işlemlik gerçek canlı veri analiziyle
# bulundu): işlemlerin %80'i (128/161) max_hold_timeout ile kapanıyor ve
# bu grup net zarar veriyor (-7.11$, %44 kazanma). 1D+4H+1H uyumu tek
# başına yeterince ayrıştırıcı değil. Hacim teyidi eklenerek "gerçek bir
# hareketin başında mıyız yoksa durgun/sessiz bir yükselişte mi
# sıkışacağız" ayrımı yapılmaya çalışılıyor.
# ⚠️ Bu eşik canlıda henüz test edilmedi - ilk tahmin değeri. Birkaç
# günlük veri sonrası panel_analiz ile gözden geçirilmeli.
HACIM_TEYIT_AKTIF = os.getenv("HACIM_TEYIT_AKTIF", "true").lower() == "true"
HACIM_TEYIT_KATSAYI = float(os.getenv("HACIM_TEYIT_KATSAYI", "1.5"))
HACIM_TEYIT_PERIYOT = int(os.getenv("HACIM_TEYIT_PERIYOT", "20"))

# KULLANICI KARARI (14.09.2026, aynı analiz): en sert SL kayıplarının
# (CATI, PROS, ZEN, DOOD, BR, PIEVERSE - toplam ~14 işlem, -13.84$) ortak
# paterni: coin girişten önce zaten güçlü pompalanmıştı, hemen ardından
# sert geri çekilme SL'i tetikledi. Pump filtresi bu "tepede giriş"
# riskini azaltmaya çalışıyor.
# ⚠️ Bu eşik de canlıda henüz test edilmedi - ilk tahmin değeri.
PUMP_FILTRE_AKTIF = os.getenv("PUMP_FILTRE_AKTIF", "true").lower() == "true"
PUMP_FILTRE_ESIK_PCT = float(os.getenv("PUMP_FILTRE_ESIK_PCT", "15.0"))

# API yükünü artırmamak için: aday_havuzu()'nun zaten çektiği
# fetch_tickers() sonucu kısa süreliğine önbelleklenir, pump_coin_mu()
# bu önbellekten okur (ekstra API çağrısı yapmaz).
TICKER_CACHE_SN = 30
_ticker_cache = {"veri": {}, "ts": 0}

# ════════════════════════════════════════════
# v3.7 YENİ: KISMİ KÂR ALMA + BREAKEVEN
# ════════════════════════════════════════════
# KULLANICI KARARI (14.09.2026): "%5 hedefe ulaşmadan pozisyon geri
# dönüyor, o zamana kadarki kâr buharlaşıyor" gözlemi üzerine eklendi.
# Mantık: pozisyon KISMI_KAR_ESIK_PCT'e ulaştığında miktarın
# KISMI_KAR_ORANI kadarı kapatılır (o kâr garanti altına alınır), kalan
# kısmın SL'i girişe (breakeven + komisyon payı) çekilir - kalan kısım
# en kötü ihtimalle nötr kapanır, ayrıca tam %5 hedefe ulaşma şansı da
# korunur.
# Eşik %1.5 (hedefin ~%30'u) seçildi: küçük hesap + 10x kaldıraçta tek
# bir SL kaybı bakiyenin önemli bir kısmını götürüyor (geçmiş veride
# görülen -1$ civarı kayıplar, ~4$'lık bakiyenin %20-25'i), bu yüzden
# erken bir eşikle "en azından bir şey garanti et" önceliklendirildi.
# Oran %50 seçildi: ne çok erken tüm pozisyonu feda edip hızlı_tp
# grubunun büyük kazançlarını (backtest/canlıda görülen +1$'ı aşan
# işlemler) kaçırmamak, ne de whipsaw riskini tam taşımak arasında denge.
# ⚠️ Bu, ortalama kazancı hafifçe düşürebilir (erken kısmi kapanışlar
# tam hedeften daha az kazandırır) ama tutarlılığı artırması beklenir -
# henüz canlıda test edilmedi, birkaç günlük veriyle değerlendirilmeli.
KISMI_KAR_AKTIF = os.getenv("KISMI_KAR_AKTIF", "true").lower() == "true"
KISMI_KAR_ESIK_PCT = float(os.getenv("KISMI_KAR_ESIK_PCT", "0.015"))
KISMI_KAR_ORANI = float(os.getenv("KISMI_KAR_ORANI", "0.5"))
BREAKEVEN_KOMISYON_PAYI = float(os.getenv("BREAKEVEN_KOMISYON_PAYI", "0.001"))

# TREND DÖNÜŞ AJANI - varsayılan KAPALI (kullanıcı kararı, hem eski
# live_bot'ta hem paper_bot_v2'de net zarar verdiği görüldü).
TREND_AJANI_AKTIF = os.getenv("TREND_AJANI_AKTIF", "false").lower() == "true"
TREND_KONTROL_ARALIGI_SN = int(os.getenv("TREND_KONTROL_ARALIGI_SN", "900"))
TREND_TERS_TEYIT_SAYISI = int(os.getenv("TREND_TERS_TEYIT_SAYISI", "2"))
TREND_TERS_TEYIT_KISMI_SAYISI = int(os.getenv("TREND_TERS_TEYIT_KISMI_SAYISI", "4"))

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/live2_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/live2_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/live2_log.json")
BLOKE_PATH = os.getenv("BLOKE_PATH", "/data/live2_bloke.json")

# TEMKİNLİ MOD (21.08.2026 kararı)
TEMKINLI_MOD_AKTIF = os.getenv("TEMKINLI_MOD_AKTIF", "true").lower() == "true"
BTC_REJIM_KONTROL_ARALIGI_SN = int(os.getenv("BTC_REJIM_KONTROL_ARALIGI_SN", "900"))
_btc_rejim_durumu = {"temkinli": False, "son_kontrol": 0}

# İZLEME LİSTESİ AJANI (21.08.2026 kararı)
IZLEME_LISTESI_BOYUTU = int(os.getenv("IZLEME_LISTESI_BOYUTU", "10"))
IZLEME_TARAMA_ARALIGI_SN = int(os.getenv("IZLEME_TARAMA_ARALIGI_SN", "900"))
IZLEME_MAX_YAS_SAAT = float(os.getenv("IZLEME_MAX_YAS_SAAT", "24"))

trade_state = {}
state_lock = threading.Lock()
acilis_rezervasyonlari = {}
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()
bloke_coinler = set()
bloke_lock = threading.Lock()

izleme_listesi = {}  # sym -> {"eklenme_zamani": ts}
izleme_lock = threading.Lock()
_son_izleme_taramasi = {"ts": 0}


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


def trade_log_kaydet(kayit):
    with log_lock:
        trade_log.append(kayit)
        veri = list(trade_log)
    atomik_yaz(TRADE_LOG_PATH, veri)


def trade_log_yukle():
    global trade_log
    trade_log = guvenli_oku(TRADE_LOG_PATH, [])


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


# v7.0: kartlara dürüst geçmiş istatistiği (garanti DEĞİL). Kaynak: 187 coin / 45 gün / 5 dk mum gerçekçi backtest:
# kartın SL/TP mantığı (SL<=%4), iz sürme, 8 saat zaman aşımı, komisyon %0.06/%0.02, giriş kayması %0.1, stop kayması %0.15,
# likidasyon, 4 pozisyon sınırı; $5 marjin, 5x. Fonlama ücreti ve elle seçim dahil değil.
ISTATISTIK_KALDIRAC = 5
ISTATISTIK_GECMIS = {
    "short": {"kazanma": 60, "ort": 2.0, "en_kotu": 22, "not": "424 işlem"},
    "long": {"kazanma": 59, "ort": 0.8, "en_kotu": 22, "not": "sadece 46 işlem, örnek küçük"},
}


def gecmis_istatistik_satiri(yon, lev=None):
    """Kartın sonuna eklenen uyarı: sinyal garanti değildir; gerçekçi backtest sonuçları."""
    g = ISTATISTIK_GECMIS.get(yon)
    if not g:
        return ""
    uyari = ""
    lev = int(lev or LEV)
    if lev != ISTATISTIK_KALDIRAC:
        uyari = f" ⚠️ Test {ISTATISTIK_KALDIRAC}x ile yapıldı, senin kaldıracın {lev}x."
    return (f"   📊 <i>Geçmiş test ({g['not']}, {ISTATISTIK_KALDIRAC}x, SL≤%4): işlemlerin ~%{g['kazanma']}'i kazandı, "
            f"işlem başına ortalama marjinin %{g['ort']:.1f}'i; en kötü işlem marjinin -%{g['en_kotu']}'i. "
            f"Kayma/komisyon varsayımdır, fonlama dahil değil.{uyari} GARANTİ YOK.</i>")


def kaldirac_ayarla(sym, lev, long_mu):
    """v7.1: Bitget izole + hedge (çift yönlü) modunda kaldıraç YÖNE göre ayrıdır; holdSide verilmezse API hata verebilir ve
    kaldıraç sessizce eski değerinde (örn. 10x) kalıyordu. Önce holdSide ile dener, olmazsa parametresiz dener.
    Döner: (başarılı_mı, hata_metni)."""
    hata = None
    for params in ({"holdSide": "long" if long_mu else "short"}, {}):
        try:
            exchange.set_leverage(lev, sym, params)
            return True, None
        except Exception as e:
            hata = e
            log.warning(f"[KALDIRAC] {sym} {lev}x params={params}: {e}")
    return False, str(hata)[:160]


def pozisyon_kaldirac_satiri(sym, long_mu, sl, beklenen_lev, beklenen_mod=None):
    """v7.1/v7.2: Pozisyon açıldıktan sonra borsadaki GERÇEK kaldıracı, marjin modunu ve likidasyon fiyatını okuyup bildirim satırı üretir.
    Beklenenden farklıysa ya da (izoleyse) likidasyon SL'ye çok yakın/öndeyse uyarır."""
    try:
        pozlar = exchange.fetch_positions([sym])
        p = next((x for x in pozlar if safe(x.get("contracts")) > 0), None)
    except Exception as e:
        log.warning(f"[POZ_KALDIRAC] {sym}: {e}")
        return "⚠️ Kaldıraç/marjin modu/likidasyon borsadan okunamadı, Bitget'te elle kontrol et.\n"
    if not p:
        return ""
    lev = safe(p.get("leverage")) or None
    liq = safe(p.get("liquidationPrice")) or None
    entry = safe(p.get("entryPrice")) or sl
    mod_g = str(p.get("marginMode") or "").lower()
    mod_g = "cross" if mod_g in ("cross", "crossed") else ("isolated" if mod_g == "isolated" else None)
    satir = ""
    if mod_g:
        satir += f"Marjin modu: {mod_etiketi(mod_g)}\n"
        if beklenen_mod and mod_g != beklenen_mod:
            satir += (f"🚨 {mod_etiketi(beklenen_mod)} bekleniyordu ama pozisyon {mod_etiketi(mod_g)} açıldı! "
                      f"Bitget'te marjin modunu elle kontrol et.\n")
    if lev:
        satir += f"Kaldıraç: {lev:.0f}x"
        if abs(lev - beklenen_lev) > 0.5:
            satir += (f"\n🚨 BEKLENEN {beklenen_lev}x ama pozisyon {lev:.0f}x açıldı! Bitget'te 'Marjin ekle' ile ya da "
                      f"kaldıracı düşürerek düzelt.")
        satir += "\n"
    if liq:
        satir += f"Likidasyon: {liq:.8g}\n"
        if mod_g != "cross":
            onde = (liq >= sl) if long_mu else (liq <= sl)
            tampon = abs(sl - liq) / entry if entry else 0
            if onde:
                satir += "🚨 LİKİDASYON SL'DEN ÖNCE GELİR, stop çalışmaz! Hemen marjin ekle ya da kaldıracı düşür.\n"
            elif tampon < 0.015:
                satir += f"⚠️ Likidasyon SL'ye çok yakın (%{tampon*100:.1f} tampon). Marjin eklemeyi düşün.\n"
    return satir


def likidasyon_mesafe_yaklasik(lev):
    """v6.6: Tahmini likidasyon mesafesi (fiyat yüzdesi, oran olarak). Bitget küçük coinlerde yüksek
    bakım marjini uyguladığı için 10x'te likidasyon ~%9.5 değil ~%5 civarında çıkıyor (SAND short
    örneği: giriş 0.07453, likidasyon 0.07803 = %4.7). Bu YAKLAŞIK bir değerdir; kesin değer için
    borsadaki 'Est. liq. price' alanına bak."""
    return max(0.01, 1.0 / max(lev, 1) - 0.05)


def mod_etiketi(mod):
    return "Cross" if mod in ("cross", "crossed") else "İzole"


def ayar_satiri(aday):
    """Kartta gösterilen güncel ayar: kaldıraç · marjin modu · marjin → pozisyon büyüklüğü."""
    lev = int(aday.get("lev") or LEV)
    marjin = float(aday.get("marjin", MANUEL_MARJIN_VARSAYILAN_USDT))
    mod = aday.get("mod") or MARJIN_MODU
    return f"   ⚙️ <b>{lev}x · {mod_etiketi(mod)} · marjin ${marjin:.2f} → pozisyon ≈${marjin*lev:.0f}</b>\n"


def marjin_modu_ayarla(sym, mod):
    """Bitget'te coin için marjin modunu ('isolated' / 'cross') ayarlar. Açık pozisyon/emir varken mod değişmez.
    Döner: (başarılı_mı, hata_metni). Zaten aynı moddaysa borsa hata verebilir; gerçek durum dolumdan sonra okunur."""
    try:
        exchange.set_margin_mode(mod, sym)
        return True, None
    except Exception as e:
        log.warning(f"[MARJIN_MODU] {sym} {mod}: {e}")
        return False, str(e)[:160]


def likidasyon_uyari_satiri(risk_orani, lev=None, mod=None):
    """SL mesafesi tahmini likidasyondan uzaksa kart için uyarı satırı döner (yoksa boş metin). Cross'ta her zaman uyarır."""
    lev = lev or LEV
    if mod == "cross":
        return ("   ⚠️ <i>CROSS: tüm bakiye ortak marjin. Stop çalışmazsa kayıp bu işlemle sınırlı kalmaz; İzole daha güvenli.</i>\n")
    liq = likidasyon_mesafe_yaklasik(lev)
    if risk_orani <= liq:
        return ""
    return (f"   ⚠️ <i>SL (%{risk_orani*100:.1f}) tahmini likidasyondan (~%{liq*100:.1f}, {lev}x) uzak: "
            f"stop çalışmadan likide olabilirsin, gerçek zarar sınırı marjin. Marjini küçük tut ya da kaldıracı düşür.</i>\n")


# ════════════════════════════════════════════
# v6.0: MANUEL ANALİZ MOTORU (RSI, trend yönü, aday tarama, swing SL/TP)
# ════════════════════════════════════════════
manuel_bekleyen = {}       # token -> aday dict (Aç/Düzenle butonları için)
manuel_limit_emirler = {}  # sym -> {order_id, sym, yon, sl, tp, qty, konulma_zamani, iz_surme}
manuel_kilit = threading.Lock()
manuel_metin_bekleyen = {}  # chat_id -> token (bir sonraki düz metin mesajı SL/TP düzenlemesi olarak okunur)
otomatik_bildirim_gecmis = {}  # "SEMBOL:yon" -> son bildirim zamanı (aynı kurulumu tekrar tekrar bildirmemek için)
ani_hareket_gecmis = {}  # "SEMBOL:yon" -> son alarm zamanı


def rsi_hesapla(kapanislar, periyot=14):
    if len(kapanislar) < periyot + 1:
        return None
    d = kapanislar.diff()
    kazanc = d.clip(lower=0).ewm(alpha=1/periyot, adjust=False).mean()
    kayip = (-d.clip(upper=0)).ewm(alpha=1/periyot, adjust=False).mean()
    if kayip.iloc[-1] == 0:
        return 100.0
    rs = kazanc.iloc[-1] / kayip.iloc[-1]
    return 100 - 100 / (1 + rs)


def trend_yon(df):
    """MA20/MA50 sıralaması + MA20 eğimine göre YUKARI/AŞAĞI/karışık. df en az 55 mum içermeli."""
    if df is None or len(df) < 55:
        return "karışık"
    ma20 = df["close"].rolling(20).mean()
    ma50 = df["close"].rolling(50).mean()
    egim = ma20.iloc[-1] - ma20.iloc[-4]
    c = df["close"].iloc[-1]
    if c > ma20.iloc[-1] > ma50.iloc[-1] and egim > 0:
        return "YUKARI"
    if c < ma20.iloc[-1] < ma50.iloc[-1] and egim < 0:
        return "AŞAĞI"
    return "karışık"


def manuel_swing_sl_tp(df1s, df4s, entry, long_mu, sl_tavan=None):
    """Son 20 adet 1S mumun dip/zirvesinden SL, son 20 adet 4S mumun
    dip/zirvesinden TP hesaplar (basit, şeffaf bir destek/direnç kuralı -
    gözle yapılan yorumun kaba bir yaklaşığı, kesin bir sinyal değil).
    R/R < MANUEL_MIN_RR ise None döner (aday elenir)."""
    if df1s is None or len(df1s) < 21 or df4s is None or len(df4s) < 21:
        return None
    if long_mu:
        dip1s = df1s["low"].iloc[-21:-1].min()
        sl = dip1s * (1 - MANUEL_SL_BUFFER_PCT)
        if sl_tavan and (entry - sl) / entry > sl_tavan:
            sl = entry * (1 - sl_tavan)      # v7.0: SL en fazla sl_tavan kadar uzakta
        risk = entry - sl
        zirve4s = df4s["high"].iloc[-21:-1].max()
        if zirve4s > entry:
            tp = min(zirve4s, entry + risk * 3)          # direnç hâlâ ileride: ona doğru hedefle, aşırı iyimseri sınırla
        else:
            tp = entry + risk * max(MANUEL_MIN_RR, 1.5)  # fiyat zaten kırılmış: görünür direnç yok, R/R'a dayalı hedef
        odul = tp - entry
    else:
        zirve1s = df1s["high"].iloc[-21:-1].max()
        sl = zirve1s * (1 + MANUEL_SL_BUFFER_PCT)
        if sl_tavan and (sl - entry) / entry > sl_tavan:
            sl = entry * (1 + sl_tavan)      # v7.0: SL en fazla sl_tavan kadar uzakta
        risk = sl - entry
        dip4s = df4s["low"].iloc[-21:-1].min()
        if dip4s < entry:
            tp = max(dip4s, entry - risk * 3)
        else:
            tp = entry - risk * max(MANUEL_MIN_RR, 1.5)
        odul = entry - tp
    if risk <= 0 or odul <= 0 or odul / risk < MANUEL_MIN_RR:
        return None
    return round(sl, 10), round(tp, 10), round(odul / risk, 2)


def manuel_aday_analiz(sym):
    """Tek bir sembolü 4S (ana filtre) + 1S (zamanlama) + 15dk (güncel fiyat)
    ile analiz eder. Temiz bir uzun/kısa kurulum yoksa None döner."""
    try:
        d4 = get_df(sym, "4h", 150)
        d1 = get_df(sym, "1h", 150)
        d15 = get_df(sym, "15m", 30)
    except Exception as e:
        log.warning(f"[MANUEL_ANALIZ] {sym}: {e}")
        return None
    if d4 is None or d1 is None or d15 is None or len(d4) < 55 or len(d1) < 55:
        return None
    y4, y1 = trend_yon(d4), trend_yon(d1)
    r4 = rsi_hesapla(d4["close"], MANUEL_RSI_PERIYOT)
    r1 = rsi_hesapla(d1["close"], MANUEL_RSI_PERIYOT)
    if r4 is None or r1 is None:
        return None
    fiyat = float(d15["close"].iloc[-1])
    ma20_1s = d1["close"].rolling(20).mean().iloc[-1]
    ma_mesafe = (fiyat / ma20_1s - 1) * 100 if ma20_1s else 0

    long_mu = None
    if y4 == "YUKARI" and y1 == "YUKARI" and r4 <= 72 and r1 <= 70 and ma_mesafe <= 5:
        long_mu = True
    elif y4 == "AŞAĞI" and y1 == "AŞAĞI" and r4 >= 28 and r1 >= 30 and ma_mesafe >= -5:
        long_mu = False
    if long_mu is None:
        return None

    sonuc = manuel_swing_sl_tp(d1, d4, fiyat, long_mu)
    if sonuc is None:
        return None
    sl, tp, rr = sonuc
    return {
        "symbol": sym, "yon": "long" if long_mu else "short", "fiyat": fiyat,
        "y4": y4, "y1": y1, "r4": round(r4, 1), "r1": round(r1, 1),
        "ma_mesafe": round(ma_mesafe, 2), "sl": sl, "tp": tp, "rr": rr,
        "zaman": time.time(),
    }


def uc_gun_degisim_pct(sym):
    """Son 72 saatteki toplam fiyat değişimini (%) döner (1S mumlarla).
    Yeterli geçmişi olmayan (yeni listelenen) coinler için None döner."""
    try:
        d = get_df(sym, "1h", 76)
    except Exception:
        return None
    if d is None or len(d) < 73:
        return None
    simdi = d["close"].iloc[-1]
    eski = d["close"].iloc[-73]
    if eski <= 0:
        return None
    return (simdi / eski - 1) * 100


def pencere_ici_hareket_ve_hacim(sym, pencere_dk):
    """Son `pencere_dk` dakikadaki fiyat değişimini (%) ve hacim çarpanını
    (bu pencere / aynı uzunluktaki önceki pencere) döner. 1dk mum kullanır,
    tamamlanmamış son mumu atar. Veri yetersizse (None, None) döner."""
    try:
        d = get_df(sym, "1m", pencere_dk * 2 + 5)
    except Exception:
        return None, None
    if d is None or len(d) < pencere_dk * 2 + 1:
        return None, None
    simdi = d["close"].iloc[-1]
    eski = d["close"].iloc[-(pencere_dk + 1)]
    if eski <= 0:
        return None, None
    hareket = (simdi / eski - 1) * 100
    hacim_simdi = d["volume"].iloc[-pencere_dk:].sum()
    hacim_once = d["volume"].iloc[-(pencere_dk * 2):-pencere_dk].sum()
    hacim_carpani = hacim_simdi / hacim_once if hacim_once > 0 else 0
    return hareket, hacim_carpani


def ani_hareket_tara():
    """İki aşamalı tarama:
    1) Son 3 günde en az ANI_HAREKET_3GUN_ESIK_PCT kadar şişmiş/düşmüş
       (likit, RWA/yavaş coin hariç) adayları bulur.
    2) O adaylardan, son ANI_HAREKET_PENCERE_DK dakikada GÜÇLÜ (hacim teyitli)
       bir TERS hareket başlamış olanları listeler - şişmiş biri düşmeye,
       düşmüş biri yükselmeye başlamışsa.
    Döner: [{"symbol", "yon" (long/short), "hareket_3g", "hareket_pencere",
             "hacim_carpani", "fiyat"}]
    """
    tickers = guncel_tickerlari_al()
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE or rwa_mi(sym):
            continue
        vol = t.get("quoteVolume") or 0
        chg = t.get("percentage")
        if vol < 1_500_000 or chg is None:
            continue
        adaylar.append((sym, chg))
    adaylar.sort(key=lambda x: -x[1])
    # geniş bir havuzdan şişmiş/düşmüş adayları bul (sadece ilk/son N değil,
    # 3 günlük gerçek harekete göre - 24s sıralaması yanıltıcı olabilir)
    havuz = [s for s, _ in adaylar[:ANI_HAREKET_TAKIP_SAYISI * 4]] + [s for s, _ in adaylar[-ANI_HAREKET_TAKIP_SAYISI * 4:]]
    havuz = list(dict.fromkeys(havuz))   # v6.7: aday sayısı az ise aynı coin iki kez taranmasın

    sonuc = []
    for sym in havuz:
        g3 = uc_gun_degisim_pct(sym)
        if g3 is None:
            continue
        if g3 >= ANI_HAREKET_3GUN_ESIK_PCT:
            tur = "sismis"      # düşüş adayı (short)
        elif g3 <= -max(ANI_HAREKET_3GUN_ESIK_PCT, ANI_HAREKET_UZUN_MIN_3GUN_PCT):
            tur = "cokmus"      # yükseliş adayı (long) - v6.7: sadece derin çöküşler (>= %40)
        else:
            continue
        hareket, hacim_carpani = pencere_ici_hareket_ve_hacim(sym, ANI_HAREKET_PENCERE_DK)
        gerekli_hacim = ANI_HAREKET_HACIM_CARPANI_KISA if tur == "sismis" else ANI_HAREKET_HACIM_CARPANI
        if hareket is None or hacim_carpani is None or hacim_carpani < gerekli_hacim:
            continue
        if tur == "sismis" and hareket <= -ANI_HAREKET_ESIK_KISA_PCT:
            try:
                fiyat = safe(tickers[sym].get("last"))
            except Exception:
                continue
            sonuc.append({"symbol": sym, "yon": "short", "hareket_3g": round(g3, 1),
                          "hareket_pencere": round(hareket, 2), "hacim_carpani": round(hacim_carpani, 2), "fiyat": fiyat})
        elif tur == "cokmus" and hareket >= ANI_HAREKET_ESIK_PCT:
            try:
                fiyat = safe(tickers[sym].get("last"))
            except Exception:
                continue
            sonuc.append({"symbol": sym, "yon": "long", "hareket_3g": round(g3, 1),
                          "hareket_pencere": round(hareket, 2), "hacim_carpani": round(hacim_carpani, 2), "fiyat": fiyat})
    return sonuc


def manuel_tarama_yap(ilerleme_cb=None):
    """İlk 20 yükselen + ilk 20 düşen likit kripto (RWA/yavaş coin hariç)
    içinden temiz kurulumları bulur. BTC bağlamını da döner."""
    tickers = guncel_tickerlari_al()
    btc_t = tickers.get("BTC/USDT:USDT", {})
    d4b, d1b = get_df("BTC/USDT:USDT", "4h", 150), get_df("BTC/USDT:USDT", "1h", 150)
    btc_baglam = {
        "y4": trend_yon(d4b) if d4b is not None else "?",
        "y1": trend_yon(d1b) if d1b is not None else "?",
        "r4": round(rsi_hesapla(d4b["close"], MANUEL_RSI_PERIYOT), 1) if d4b is not None else None,
        "r1": round(rsi_hesapla(d1b["close"], MANUEL_RSI_PERIYOT), 1) if d1b is not None else None,
        "chg24": btc_t.get("percentage"),
    }
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE or rwa_mi(sym):
            continue
        vol = t.get("quoteVolume") or 0
        chg = t.get("percentage")
        if vol < 1_500_000 or chg is None:
            continue
        adaylar.append((sym, chg, vol))
    adaylar.sort(key=lambda x: -x[1])
    havuz = [s for s, _, _ in adaylar[:20]] + [s for s, _, _ in adaylar[-20:]]

    bulunanlar = []
    for i, sym in enumerate(havuz):
        if ilerleme_cb and i % 8 == 0:
            ilerleme_cb(i, len(havuz))
        sonuc = manuel_aday_analiz(sym)
        if sonuc:
            bulunanlar.append(sonuc)
    bulunanlar.sort(key=lambda x: -x["rr"])
    return bulunanlar[:MANUEL_MAKS_KART], btc_baglam


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


def hesapla_marjin(bakiye):
    """v3.7 GÜNCELLEME (14.09.2026, kullanıcı kararı - 'kasa büyümesi'
    isteğiyle bulundu): küçük hesaplarda MARJIN_TABAN_USDT tek başına
    bakiyenin çok büyük bir kısmını tek işleme kilitleyebiliyordu (örn.
    4.26$ bakiyede taban $2 = bakiyenin %47'si). Bu, MAX_POS'un
    çeşitlendirme amacını fiilen boşa çıkarıyordu - pratikte 1-2
    pozisyondan fazla açılamıyordu, tek bir kötü SL kasanın büyük bir
    dilimini götürüyordu. Efektif taban artık
    min(MARJIN_TABAN_USDT, bakiye/MAX_POS) - bakiye küçükken pozisyon
    boyutu küçülür (çeşitlendirme korunur, tek işlem riski azalır),
    bakiye MARJIN_TABAN_USDT*MAX_POS'u (şu an $8) geçince normal tabana
    otomatik döner - bileşik büyüme mekanizmasına (RISK_PCT_BAKIYE)
    dokunulmadı, sadece küçük bakiye durumundaki taban davranışı
    düzeltildi."""
    if RISK_PCT_BAKIYE <= 0 or bakiye is None or bakiye <= 0:
        return SABIT_MARJIN_USDT
    efektif_taban = min(MARJIN_TABAN_USDT, max(bakiye / max(MAX_POS, 1), 0.5))
    marjin = bakiye * RISK_PCT_BAKIYE
    marjin = max(efektif_taban, min(MARJIN_TAVAN_USDT, marjin))
    return marjin


_market_cache = {"markets": None, "ts": 0}


def market_bilgisi_al():
    if _market_cache["markets"] is None or (time.time() - _market_cache["ts"]) > 3600:
        try:
            _market_cache["markets"] = exchange.load_markets()
            _market_cache["ts"] = time.time()
        except Exception as e:
            log.warning(f"[MARKET_BILGI] {e}")
    return _market_cache["markets"] or {}


def rwa_mi(sym):
    """Borsa bu sembolü hisse/ETF/emtia (Real World Asset) olarak işaretlediyse True (info.isRwa == 'YES').
    Market bilgisi alınamazsa False döner (dışlama yapılamaz, kripto gibi davranılır)."""
    try:
        m = market_bilgisi_al().get(sym) or {}
        return str((m.get("info") or {}).get("isRwa", "")).upper() == "YES"
    except Exception:
        return False


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


def guncel_tickerlari_al():
    """v3.6 YENİ: fetch_tickers() sonucunu kısa süreliğine önbellekler.
    aday_havuzu() ve pump_coin_mu() aynı önbelleği paylaşır - böylece
    pump filtresi eklenmesi ekstra API çağrısı yaratmaz."""
    if time.time() - _ticker_cache["ts"] < TICKER_CACHE_SN and _ticker_cache["veri"]:
        return _ticker_cache["veri"]
    try:
        _ticker_cache["veri"] = exchange.fetch_tickers()
        _ticker_cache["ts"] = time.time()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
    return _ticker_cache["veri"]


def aday_havuzu():
    tickers = guncel_tickerlari_al()
    if not tickers:
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


def genis_evren_listesi():
    tickers = guncel_tickerlari_al()
    if not tickers:
        return []
    markets = market_bilgisi_al()
    tumu = []
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
        tumu.append(sym)
    return tumu


def pump_coin_mu(sym):
    """v3.6 YENİ: coin son 24 saatte PUMP_FILTRE_ESIK_PCT üzerinde
    yükselmişse True döner - bu coinlere LONG girişi reddedilir.
    KULLANICI KARARI (14.09.2026, gerçek veri analiziyle bulundu): en
    sert SL kayıplarının ortak paterni, coin zaten aşırı pompalanmışken
    girilmiş olmasıydı (tepe civarında giriş -> sert geri çekilme).
    API yükü YOK: guncel_tickerlari_al() önbelleğinden okur, ekstra
    fetch_ticker çağrısı yapmaz."""
    if not PUMP_FILTRE_AKTIF:
        return False
    tickers = guncel_tickerlari_al()
    t = tickers.get(sym)
    if not t:
        return False
    chg = t.get("percentage")
    if chg is None:
        return False
    return chg > PUMP_FILTRE_ESIK_PCT


def hacim_teyit_var_mi(df_15m, periyot=HACIM_TEYIT_PERIYOT):
    """v3.6 YENİ: son 15m mumun hacmi, önceki `periyot` mumun ortalama
    hacminin en az HACIM_TEYIT_KATSAYI katı olmalı. KULLANICI KARARI
    (14.09.2026, gerçek veri analiziyle bulundu): işlemlerin %80'i
    max_hold_timeout ile (hafif eksi) kapanıyordu - bunların çoğu muhtemelen
    'sessiz', gerçek alım ilgisi olmayan fiyat hareketleriydi. Hacim teyidi
    bu sessiz sinyalleri elemeye çalışır."""
    if not HACIM_TEYIT_AKTIF:
        return True
    if df_15m is None or len(df_15m) < periyot + 1:
        return False
    ort_hacim = df_15m["volume"].iloc[-(periyot + 1):-1].mean()
    son_hacim = df_15m["volume"].iloc[-1]
    if pd.isna(ort_hacim) or ort_hacim <= 0:
        return False
    return son_hacim >= ort_hacim * HACIM_TEYIT_KATSAYI


def btc_temkinli_mod_mu():
    if time.time() - _btc_rejim_durumu["son_kontrol"] < BTC_REJIM_KONTROL_ARALIGI_SN:
        return _btc_rejim_durumu["temkinli"]
    try:
        df_1d = get_df("BTC/USDT:USDT", "1d", MA_PERIYOT + 10)
        df_4h = get_df("BTC/USDT:USDT", "4h", MA_PERIYOT + 5)
        y1d = trend_yonu(df_1d)
        y4h = trend_yonu(df_4h)
        yeni_durum = (y1d == "dusus" and y4h == "dusus")
    except Exception as e:
        log.warning(f"[BTC_REJIM] {e}")
        return _btc_rejim_durumu["temkinli"]

    onceki = _btc_rejim_durumu["temkinli"]
    _btc_rejim_durumu["temkinli"] = yeni_durum
    _btc_rejim_durumu["son_kontrol"] = time.time()
    if yeni_durum != onceki:
        if yeni_durum:
            durdurma_metni = ("YENİ POZİSYON AÇMA TAMAMEN DURDU" if TEMKINLI_MOD_TAM_DURDURMA
                               else "MAX_POS geçici olarak yarıya indi")
            tg(f"⚠️ BTC 1D+4H düşüşe döndü — TEMKİNLİ MOD aktif, "
               f"{durdurma_metni}. Açık pozisyonlar etkilenmez, kendi "
               f"SL/TP/kısmi kâr alma mantığıyla yönetilmeye devam eder.")
        else:
            tg("✅ BTC 1D+4H yeniden yükselişte — TEMKİNLİ MOD kapandı, "
               "yeni pozisyon açma normale döndü.")
    return yeni_durum


# v3.8 YENİ: TEMKİNLİ MOD DAVRANIŞI SIKILAŞTIRILDI
# KULLANICI KARARI (14.09.2026): "piyasa düşüşe dönünce bot bocalıyor,
# kârlar eriyip zarara dönüyor" gözlemi üzerine konuşuldu. Değerlendirilen
# alternatif ("trend dönünce pozisyonu tersine çevir / SHORT'a geç")
# BİLİNÇLİ OLARAK REDDEDİLDİ - kodun kendi geçmişinde zaten denenmiş ve
# başarısız olmuş bir yaklaşım (SHORT özelliği 10.09.2026'da eklenip
# ilk gerçek işlemde "short squeeze" ile kayıp verip 11.09.2026'da
# kapatılmıştı). Trend dönüş sinyali (1D+4H+1H'nin üçünün de dönmesi)
# doğası gereği GEÇ gelir - bu noktada pozisyon tersine çevirmek, geçici
# bir sıçramaya (whipsaw) yakalanıp hem eski hem yeni yönde kayıp verme
# riskini artırır (nitekim SLX işleminde tam bu olmuştu).
# Bunun yerine daha güvenli, tek yönlü bir önlem seçildi: BTC'nin kendi
# 1D+4H trendi düşüşe dönerse, YENİ pozisyon açmayı TAMAMEN durdur (önceden
# sadece MAX_POS yarıya iniyordu). Açık pozisyonlara DOKUNULMAZ - onlar
# kendi SL/TP/kısmi kâr alma mantığıyla normal şekilde yönetilmeye devam
# eder. Amaç: piyasa net olarak zayıflarken üstüne yeni risk eklememek,
# ama var olan pozisyonları panikle kapatıp yön değiştirerek ekstra risk
# yaratmamak.
# v3.9 GÜNCELLEME (14.09.2026, kullanıcı kararıyla): v3.8'deki "BTC düşerse
# yeni pozisyonu TAMAMEN durdur" kararı geri alındı. Neden: orijinal kodun
# kendi geçmişinde bu tam olarak denenmiş ve terk edilmişti - "bir altcoin
# BTC'den bağımsız gerçekten güçlü olabilir, coin'leri tamamen engellemek
# yanlış çıkmıştı" notuyla. Kullanıcı haklı olarak bunu hatırlattı: BTC
# düşerken bağımsız pump yapan güçlü bir coin fırsatını tamamen kaçırmak
# istemiyoruz.
# YENİ YAKLAŞIM: MAX_POS yine yarıya iner (v3.7 ve öncesi davranış), AMA
# o dönemde girecek coin için trend gücü eşiği YÜKSELTİLİR
# (MIN_4H_TREND_GUCU_PCT yerine MIN_4H_TREND_GUCU_PCT_TEMKINLI kullanılır).
# Mantık: "piyasa genel olarak zayıfken daha seçici ol" - zayıf/sınırda
# coinler elenir, sadece BTC'den GERÇEKTEN bağımsız, güçlü hareket eden
# coinler işleme girebilir. Bu, "hiçbir şey yapma" (eski v3.7) ile
# "her şeyi durdur" (v3.8) arasında bir orta yol.
TEMKINLI_MOD_TAM_DURDURMA = os.getenv("TEMKINLI_MOD_TAM_DURDURMA", "false").lower() == "true"
MIN_4H_TREND_GUCU_PCT_TEMKINLI = float(os.getenv("MIN_4H_TREND_GUCU_PCT_TEMKINLI", "4.0"))


def efektif_max_pos():
    if not TEMKINLI_MOD_AKTIF:
        return MAX_POS
    if btc_temkinli_mod_mu():
        if TEMKINLI_MOD_TAM_DURDURMA:
            return 0
        return max(1, MAX_POS // 2)
    return MAX_POS


# ════════════════════════════════════════════
# ÜÇLÜ ZAMAN DİLİMİ UYUM SİNYALİ (1D+4H+1H) + SADECE LONG
# ════════════════════════════════════════════
def trend_yonu(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma):
        return None
    return "yukselis" if fiyat > ma else "dusus"


def trend_gucu_pct(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma) or ma == 0:
        return None
    return (fiyat - ma) / ma * 100


def aktif_strateji_modu():
    """v4.0 YENİ: STRATEJI_MODU='otomatik' ise BTC rejimine göre karar
    verir - BTC zayıfken (temkinli mod aktif) 'yukselen', güçlüyken
    'trend' döner. Sabit 'trend' ya da 'yukselen' verilmişse onu kullanır."""
    if STRATEJI_MODU in ("trend", "yukselen"):
        return STRATEJI_MODU
    # otomatik
    if TEMKINLI_MOD_AKTIF and btc_temkinli_mod_mu():
        return "yukselen"
    return "trend"


def yukselen_coin_havuzu():
    """v4.9 KRİTİK DÜZELTME (23.09.2026, güncel gerçek veriyle backtest
    edilip bulundu): v4.6/v4.7'de sadece "yön pozitif mi" (chg>0)
    filtresi kullanılıyordu - bu ÇOK GEVŞEK bir filtre (coinlerin
    neredeyse yarısını geçiriyor), asıl seçiciliği sağlayan ÖNCEKİ
    YÜZDELİK DİLİM sıralaması (üst %X) kaybedilmişti. Son 10 günlük
    gerçek veride büyük ölçekli backtest yapıldığında: sadece
    yön+hacim+zirve filtresiyle (yüzdelik sıralama OLMADAN) net
    ZARARLI çıktı - yüzdelik dilim sıralaması GERİ GETİRİLİNCE
    (üst %20) net pozitife döndü. Artık coinler, son 24s getirisine
    göre TÜM ADAYLAR ARASINDA sıralanıp üst dilime girenler seçiliyor
    (basit "pozitif mi" sorusu değil, "ne kadar güçlü" sorusu)."""
    tickers = guncel_tickerlari_al()
    if not tickers:
        return []
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE:
            continue
        if not RWA_HISSE_DAHIL and rwa_mi(sym):
            continue
        vol = t.get("quoteVolume") or 0
        if vol < 300000:
            continue
        chg = t.get("percentage")
        if chg is None:
            continue
        adaylar.append((sym, chg))
    if not adaylar:
        return []
    skorlar = sorted([s for _, s in adaylar])
    esik_idx = min(int(len(skorlar) * YUKSELEN_UST_YUZDELIK), len(skorlar) - 1)
    esik_deger = skorlar[esik_idx]
    # v5.5: "üst dilim eşiği <= 0 ise hiç aday verme" kuralı (v4.9'da testsiz
    # eklenmişti) artık VARSAYILAN KAPALI. Backtest'te bu koşulda açılan
    # işlemler daha kötü değil, biraz daha iyi çıktı (eski dönem ort. +%0.85
    # vs genel +%0.67; taze dönem +%1.24 vs +%0.64; örnekler küçük: 84/28 işlem).
    # Kanıt olmadan botu tamamen durdurduğu için kapatıldı; istenirse
    # YUKSELEN_NEGATIF_ESIK_ENGEL=true ile geri açılabilir.
    if esik_deger <= 0 and YUKSELEN_NEGATIF_ESIK_ENGEL:
        return []
    return [sym for sym, s in adaylar if s >= esik_deger]


def yukselen_coin_sinyal(sym):
    """Üst dilimdeki coin için: hacim teyidi + yükselen kapanış şartı
    (paper bot'taki giris_sinyali ile birebir aynı mantık).

    v4.1 YENİ (17.09.2026, kullanıcı gözlemiyle bulundu): PIEVERSE ve
    SUI gibi coinlerde "tam pompanın zirvesinde giriş" görüldü (fiyat
    zaten sert yükselmiş, hemen ardından geri çekilmiş, bot tam tepede
    girmiş). ZIRVEDEN_MIN_MESAFE_PCT filtresi eklendi - giriş fiyatı,
    son ZIRVE_LOOKBACK mumun en yüksek noktasından en az bu kadar aşağıda
    olmalı (coin biraz geri çekilmiş olsun, tam zirvede alım yapılmasın).
    Backtest'te (136 coin/~51 gün) doğrulandı: %1.5 mesafe filtresiyle
    kazanma oranı %48.9'dan %51.6'ya, işlem başına ortalama kazanç
    $2.50'den $3.26'ya çıktı - bedeli işlem sayısının azalması (daha
    seçici hale gelmesi)."""
    if pump_coin_mu(sym):  # aşırı pompalanmış coinlere yine de girmeyelim
        return None
    df_15m = get_df(sym, "15m", max(HACIM_TEYIT_PERIYOT, 20, ZIRVE_LOOKBACK) + 5)
    if df_15m is None or len(df_15m) < HACIM_TEYIT_PERIYOT + 2:
        return None
    son_mum = df_15m.iloc[-1]
    ort_hacim = df_15m["volume"].iloc[-(HACIM_TEYIT_PERIYOT + 1):-1].mean()
    if pd.isna(ort_hacim) or ort_hacim <= 0 or son_mum["volume"] < ort_hacim * YUKSELEN_HACIM_KATSAYI:
        return None
    if son_mum["close"] <= son_mum["open"]:
        return None

    # v5.2 YENİ (kullanıcı gözlemiyle bulundu - ZRO örneği: giriş sonrası
    # hiç toparlanmadan sert düşen işlemler): mumun GÖVDE GÜCÜ kontrolü.
    # Sadece "kapanış açılıştan yüksek mi" (zayıf/kararsız mumlar da bu
    # şartı geçebilir) değil, gövdenin toplam mum aralığına oranına
    # bakılıyor - küçük gövdeli/uzun fitilli "kararsız" mumlar elenir.
    # Backtest'te (güncel veri) doğrulandı: %45 eşiğiyle kazanma oranı
    # %59.6'dan ~%60.8'e çıktı, işlem başına ortalama kazanç $0.59'dan
    # ~$0.78'e yükseldi - bedeli işlem sayısının azalması (daha seçici).
    toplam_aralik = son_mum["high"] - son_mum["low"]
    if toplam_aralik <= 0:
        return None
    govde = son_mum["close"] - son_mum["open"]
    govde_oran = govde / toplam_aralik
    if govde_oran < YUKSELEN_MIN_GOVDE_ORANI:
        return None

    # v4.1 YENİ: zirveden yeterince uzak (tam tepede değil) mi kontrolü
    if len(df_15m) >= ZIRVE_LOOKBACK:
        zirve = df_15m["high"].iloc[-ZIRVE_LOOKBACK:].max()
        if zirve > 0:
            zirve_mesafe = (zirve - son_mum["close"]) / zirve
            if zirve_mesafe < ZIRVEDEN_MIN_MESAFE_PCT:
                return None

    # v4.7 YENİ (kullanıcı talimatıyla): ANLIK volatilite kontrolü - 24
    # saatlik geçmişe değil, işlem alınacağı O ANA (son ANLIK_VOLATILITE_MUM
    # mum, örn. son 1 saat) bakılıyor. Bu, "işlem alırken o an hareketli
    # olan coin" isteğini karşılıyor - 24s'lik ölçüm gecikmeli kalabiliyordu.
    son_pencere = df_15m.iloc[-ANLIK_VOLATILITE_MUM:]
    if len(son_pencere) >= 2 and son_mum["close"] > 0:
        anlik_volatilite = (son_pencere["high"].max() - son_pencere["low"].min()) / son_mum["close"] * 100
        if anlik_volatilite < ANLIK_VOLATILITE_MIN_PCT:
            return None

    # gercek_pozisyon_ac'ın beklediği formatla uyumlu: swing_nokta yerine
    # basit sabit SL kullanacağız (aşağıda _gercek_pozisyon_ac_ic'te
    # swing_nokta None ise sabit yüzde SL'e düşülüyor)
    return {"symbol": sym, "yon": "long", "entry": float(son_mum["close"]),
            "swing_nokta": None, "1d": "-", "4h": "-", "1h": "-", "mum_ts": int(son_mum["ts"])}


def ucyon_sinyal(sym):
    """v4.0: aktif strateji moduna göre trend-uyum ya da yukselen-coin
    sinyaline yönlendirir."""
    mod = aktif_strateji_modu()
    if mod == "yukselen":
        return yukselen_coin_sinyal(sym)
    return trend_uyum_sinyal(sym)


def trend_uyum_sinyal(sym):
    df_1d = get_df(sym, "1d", MA_PERIYOT + 10)
    df_4h = get_df(sym, "4h", MA_PERIYOT + 5)
    df_1h = get_df(sym, "1h", MA_PERIYOT + 5)

    yon_1d = trend_yonu(df_1d)
    yon_4h = trend_yonu(df_4h)
    yon_1h = trend_yonu(df_1h)
    guc_4h = trend_gucu_pct(df_4h)

    # v3.9 YENİ: BTC (piyasa geneli) düşüşteyken eşik yükseltilir - sadece
    # BTC'den gerçekten bağımsız, güçlü hareket eden coinler geçer. BTC
    # yükselişte/karışıkken normal eşik (MIN_4H_TREND_GUCU_PCT) kullanılır.
    if TEMKINLI_MOD_AKTIF and btc_temkinli_mod_mu():
        aktif_esik = MIN_4H_TREND_GUCU_PCT_TEMKINLI
    else:
        aktif_esik = MIN_4H_TREND_GUCU_PCT

    if yon_1d == "yukselis" and yon_4h == "yukselis" and yon_1h == "yukselis":
        if guc_4h is None or guc_4h < aktif_esik:
            return None
        return _ucyon_sinyal_yon(sym, "long", yon_1d, yon_4h, yon_1h)

    if SHORT_AKTIF and yon_1d == "dusus" and yon_4h == "dusus" and yon_1h == "dusus":
        if guc_4h is None or guc_4h > -aktif_esik:
            return None
        return _ucyon_sinyal_yon(sym, "short", yon_1d, yon_4h, yon_1h)

    return None


def _ucyon_sinyal_yon(sym, yon, yon_1d, yon_4h, yon_1h):
    df_15m = get_df(sym, "15m", max(LOOKBACK_15M, HACIM_TEYIT_PERIYOT) + 5)
    if df_15m is None or len(df_15m) < LOOKBACK_15M + 2:
        return None

    pencere = df_15m.iloc[-(LOOKBACK_15M + 1):-1]
    son_mum = df_15m.iloc[-1]
    son_3_idx = pencere.index[-3:]

    if yon == "long":
        swing_nokta = pencere["low"].min()
        ext_idx = pencere["low"].idxmin()
        tetik_yakin = ext_idx in son_3_idx
        kapanis_uygun = son_mum["close"] > son_mum["open"]
        gecerli = tetik_yakin and kapanis_uygun and son_mum["close"] > swing_nokta
        mesafe = (son_mum["close"] - swing_nokta) / swing_nokta if gecerli else None
    else:
        swing_nokta = pencere["high"].max()
        ext_idx = pencere["high"].idxmax()
        tetik_yakin = ext_idx in son_3_idx
        kapanis_uygun = son_mum["close"] < son_mum["open"]
        gecerli = tetik_yakin and kapanis_uygun and son_mum["close"] < swing_nokta
        mesafe = (swing_nokta - son_mum["close"]) / swing_nokta if gecerli else None

    if not gecerli:
        return None
    if mesafe > GIRIS_MAX_DIP_MESAFE:
        return None

    # ── v3.6 YENİ FİLTRE 1: HACİM TEYİDİ ──
    # Sessiz (gerçek alım ilgisi olmayan) hareketleri eler. Bunlar canlı
    # veride max_hold_timeout ile hafif eksi kapanan işlemlerin büyük
    # kısmını oluşturuyordu (128/161 işlem, net -7.11$, %44 kazanma).
    if not hacim_teyit_var_mi(df_15m):
        return None

    # ── v3.6 YENİ FİLTRE 2: PUMP FİLTRESİ ──
    # Coin zaten aşırı pompalanmışsa LONG girişini reddet - canlı veride
    # en sert SL kayıplarının ortak paterni buydu (tepede giriş -> sert
    # geri çekilme). SHORT'a bu filtre uygulanmıyor (mantığı ters olurdu,
    # ayrıca SHORT şu an zaten kapalı).
    if yon == "long" and pump_coin_mu(sym):
        return None

    return {"symbol": sym, "entry": float(son_mum["close"]), "swing_nokta": float(swing_nokta),
            "yon": yon, "1d": yon_1d, "4h": yon_4h, "1h": yon_1h}


def iki_uzerinden_uc_kontrol(sym):
    df_1d = get_df(sym, "1d", MA_PERIYOT + 10)
    df_4h = get_df(sym, "4h", MA_PERIYOT + 5)
    yon_1d = trend_yonu(df_1d)
    yon_4h = trend_yonu(df_4h)
    if yon_1d == "yukselis" and yon_4h == "yukselis":
        return True
    if SHORT_AKTIF and yon_1d == "dusus" and yon_4h == "dusus":
        return True
    return False


# ════════════════════════════════════════════
# GERÇEK POZİSYON AÇMA/KAPATMA
# ════════════════════════════════════════════
def acilis_basarisiz_cooldown_uygula(sym):
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()


def manuel_limit_ac(aday, sl, tp, marjin=None):
    """Kullanıcının onayladığı adayı LİMİT emirle açar (aday['fiyat']'tan).
    marjin=None ise MANUEL_MARJIN_VARSAYILAN_USDT kullanılır, verilirse o
    kullanılır (biz/kullanıcı elle belirler). Emir hemen dolmaz;
    manuel_limit_loop doluşu bekler, dolunca SL/TP kurar.

    v6.1: Eksik/hatalı işlem açılmasını önlemek için kapsamlı doğrulama -
    sembol formatı, yön, giriş/SL/TP'nin doğru tarafta olup olmadığı, R/R,
    marjin sınırları hepsi burada kontrol edilir; herhangi biri geçersizse
    HİÇBİR borsa çağrısı yapılmadan (False, açık sebep) döner."""
    # ── Girdi doğrulama (borsaya hiçbir şey gönderilmeden önce) ──
    sym = aday.get("symbol", "")
    if not sym or "/" not in sym:
        return False, f"Geçersiz sembol: '{sym}'."
    yon = aday.get("yon")
    if yon not in ("long", "short"):
        return False, f"Geçersiz yön: '{yon}' (long ya da short olmalı)."
    long_mu = yon == "long"
    entry_hedef = safe(aday.get("fiyat"))
    sl = safe(sl); tp = safe(tp)
    if entry_hedef <= 0 or sl <= 0 or tp <= 0:
        return False, "Giriş, SL ve TP pozitif sayı olmalı."
    if long_mu and not (sl < entry_hedef < tp):
        return False, f"UZUN işlemde SL < Giriş < TP olmalı (SL={sl:.8g}, Giriş={entry_hedef:.8g}, TP={tp:.8g})."
    if not long_mu and not (tp < entry_hedef < sl):
        return False, f"KISA işlemde TP < Giriş < SL olmalı (TP={tp:.8g}, Giriş={entry_hedef:.8g}, SL={sl:.8g})."
    risk_pct = abs(entry_hedef - sl) / entry_hedef
    if risk_pct > 0.25:
        return False, f"Stop mesafesi çok geniş (%{risk_pct*100:.1f}) - girdileri kontrol et."
    if marjin is not None:
        marjin = safe(marjin)
        if marjin <= 0:
            return False, f"Marjin pozitif olmalı (girilen: {marjin})."

    with state_lock:
        if sym in trade_state or sym in acilis_rezervasyonlari or sym in manuel_limit_emirler:
            return False, "Bu sembolde zaten açık bir pozisyon ya da bekleyen emir var."
        if len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
            return False, f"Maksimum pozisyon sayısına ({efektif_max_pos()}) ulaşıldı."
    bakiye = gercek_bakiye_al()
    if not bakiye or bakiye <= 0:
        return False, "Bakiye alınamadı."

    marjin_istenen = MANUEL_MARJIN_VARSAYILAN_USDT if marjin is None else marjin
    if marjin_istenen > bakiye * 0.95:
        return False, (f"İstenen marjin (${marjin_istenen:.2f}) bakiyenin (${bakiye:.2f}) çoğunu/tamamını kullanıyor "
                        f"- reddedildi. En fazla ${bakiye*0.95:.2f} kullanılabilir.")
    marjin_kullanilan = marjin_istenen

    try:
        lev_ham = aday.get("lev")
        lev_istenen = LEV if lev_ham is None else int(lev_ham)     # 0 gibi açık geçersiz değer varsayılana düşmesin, reddedilsin
    except Exception:
        return False, f"Geçersiz kaldıraç: {aday.get('lev')}"
    if lev_istenen < 1:
        return False, f"Geçersiz kaldıraç: {lev_istenen}"
    mod = str(aday.get("mod") or MARJIN_MODU).lower()
    mod = "cross" if mod == "crossed" else mod
    if mod not in ("isolated", "cross"):
        return False, f"Geçersiz marjin modu: {mod} (isolated ya da cross olmalı)."
    LEV_KULLANILAN = sembol_max_kaldirac(sym, lev_istenen)
    notional = marjin_kullanilan * LEV_KULLANILAN
    amount = notional / entry_hedef
    try:
        qty = float(exchange.amount_to_precision(sym, amount))
        fiyat_p = float(exchange.price_to_precision(sym, entry_hedef))
    except Exception as e:
        return False, f"Miktar/fiyat hesaplanamadı: {e}"
    if qty <= 0:
        return False, "Hesaplanan miktar sıfır."
    mod_ok, mod_hata = marjin_modu_ayarla(sym, mod)      # önce marjin modu, sonra kaldıraç
    mod_uyari = "" if mod_ok else (f"⚠️ Marjin modu ({mod_etiketi(mod)}) ayarlanamadı ({mod_hata}). Zaten o moddaysa sorun değil; "
                                   f"açık pozisyon/emir varken mod değişmez. Açılınca kontrol et.\n")
    kaldirac_ok, kaldirac_hata = kaldirac_ayarla(sym, LEV_KULLANILAN, long_mu)
    kaldirac_uyari = "" if kaldirac_ok else (f"⚠️ Kaldıraç {LEV_KULLANILAN}x AYARLANAMADI ({kaldirac_hata}). Pozisyon Bitget'teki "
                                             f"mevcut kaldıraçla açılabilir; açılınca kontrol et.\n")
    yon_str = "buy" if long_mu else "sell"
    try:
        emir = exchange.create_order(sym, "limit", yon_str, qty, fiyat_p)
    except Exception as e:
        return False, f"Limit emir gönderilemedi: {e}"
    with manuel_kilit:
        manuel_limit_emirler[sym] = {
            "order_id": emir.get("id"), "sym": sym, "yon": aday["yon"], "qty": qty,
            "entry_hedef": fiyat_p, "sl": sl, "tp": tp, "konulma_zamani": time.time(),
            "1d": "-", "4h": aday.get("y4", "-"), "1h": aday.get("y1", "-"), "lev": LEV_KULLANILAN, "mod": mod,
        }
    durumu_diske_yaz()
    tg(f"📝 MANUEL LİMİT EMİR: {sym} {'LONG' if long_mu else 'SHORT'} @ {fiyat_p:.8g}\n"
       f"Marjin: ${marjin_kullanilan:.2f} ({LEV_KULLANILAN}x {mod_etiketi(mod)}, pozisyon ≈${notional:.2f})\n"
       f"Miktar: {qty} | SL: {sl:.8g} | TP: {tp:.8g}\n"
       f"{mod_uyari}"
       f"{kaldirac_uyari}"
       f"{likidasyon_uyari_satiri(risk_pct, LEV_KULLANILAN, mod).replace('<i>', '').replace('</i>', '')}"
       f"Emir {MANUEL_LIMIT_TIMEOUT_SN//3600} saat içinde dolmazsa otomatik iptal edilir.")
    return True, f"{sym} için limit emir gönderildi ({fiyat_p:.8g}), marjin ${marjin_kullanilan:.2f}."


def manuel_limit_iptal(sym, sebep="kullanıcı isteğiyle"):
    with manuel_kilit:
        kayit = manuel_limit_emirler.pop(sym, None)
    if not kayit:
        return False
    try:
        exchange.cancel_order(kayit["order_id"], sym)
    except Exception as e:
        log.warning(f"[MANUEL_IPTAL] {sym}: {e}")
    durumu_diske_yaz()
    tg(f"🗑️ {sym} bekleyen limit emri iptal edildi ({sebep}).")
    return True


def tum_pozisyonlari_kapat():
    """Acil durdurma: tüm açık pozisyonları piyasa fiyatından kapatır ve
    bekleyen tüm manuel limit emirlerini iptal eder. (kapatilan, iptal_edilen) döner."""
    with state_lock:
        durumlar = dict(trade_state)
    kapatilan = []
    for sym in durumlar:
        try:
            basarili, _ = gercek_pozisyon_kapat(sym, "manuel_hepsini_kapat")
            if basarili:
                kapatilan.append(sym)
        except Exception as e:
            log.warning(f"[HEPSINI_KAPAT] {sym}: {e}")
    with manuel_kilit:
        bekleyenler = list(manuel_limit_emirler.keys())
    iptal_edilen = [s for s in bekleyenler if manuel_limit_iptal(s, "acil durdurma - tümünü kapat")]
    return kapatilan, iptal_edilen


PANEL_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sadik Futures Bot — Panel</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.1.3/lightweight-charts.standalone.production.min.js"></script>
<style>
  :root{--bg:#0b1220;--panel:#111a2e;--panel2:#0f1830;--border:#1f2c47;--txt:#e7edf7;--muted:#8695b3;
        --green:#22c55e;--red:#ef4444;--blue:#3b82f6;--purple:#8b5cf6;--orange:#f59e0b;--yellow:#eab308;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;}
  header{display:flex;align-items:center;justify-content:space-between;padding:14px 22px;background:var(--panel);border-bottom:1px solid var(--border);flex-wrap:wrap;gap:10px}
  .brand{display:flex;align-items:center;gap:12px}
  .brand .logo{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,var(--blue),var(--purple));display:flex;align-items:center;justify-content:center;font-size:20px}
  .brand h1{font-size:17px;margin:0}
  .brand p{font-size:12px;color:var(--muted);margin:0}
  .status-chip{display:flex;align-items:center;gap:6px;background:#0f2a1a;border:1px solid #1e4a2d;color:var(--green);padding:5px 12px;border-radius:20px;font-size:12px;font-weight:600}
  .status-chip.off{background:#2a0f0f;border-color:#4a1e1e;color:var(--red)}
  .dot{width:8px;height:8px;border-radius:50%;background:currentColor}
  .updated{font-size:11px;color:var(--muted)}
  .grid{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:16px;padding:18px;max-width:1600px;margin:0 auto}
  @media(max-width:1100px){.grid{grid-template-columns:1fr}}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:16px;margin-bottom:16px}
  .card h2{font-size:14px;margin:0 0 12px;display:flex;align-items:center;gap:8px;color:#cfd8ea}
  .row{display:flex;gap:10px;flex-wrap:wrap}
  button{cursor:pointer;border:none;border-radius:9px;padding:11px 14px;font-weight:600;font-size:13px;color:#fff;transition:.15s}
  button:active{transform:scale(.97)}
  .btn-green{background:var(--green)} .btn-red{background:var(--red)} .btn-blue{background:var(--blue)}
  .btn-purple{background:var(--purple)} .btn-outline{background:#182238;border:1px solid var(--border);color:var(--txt)}
  .btn-orange{background:var(--orange)}
  button:disabled{opacity:.45;cursor:not-allowed}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  th{text-align:left;color:var(--muted);font-weight:500;padding:6px 8px;border-bottom:1px solid var(--border)}
  td{padding:8px;border-bottom:1px solid #16203a}
  .pill{padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700}
  .pill.long{background:#0f2a1a;color:var(--green)} .pill.short{background:#2a0f0f;color:var(--red)}
  .pill.bekleyen{background:#2a230f;color:var(--yellow)}
  .g{color:var(--green)} .r{color:var(--red)} .muted{color:var(--muted)}
  .statline{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #16203a;font-size:13px}
  .statline:last-child{border:0}
  input,select{background:#0d1729;border:1px solid var(--border);color:var(--txt);border-radius:8px;padding:8px 10px;font-size:13px;width:100%}
  label{font-size:11px;color:var(--muted);display:block;margin-bottom:4px}
  .field{margin-bottom:10px}
  #chart{width:100%;height:280px}
  .tf-btn{background:#182238;border:1px solid var(--border);color:var(--muted);padding:5px 10px;border-radius:6px;font-size:11px;font-weight:600}
  .tf-btn.active{background:var(--blue);color:#fff;border-color:var(--blue)}
  .lockscreen{position:fixed;inset:0;background:var(--bg);display:flex;align-items:center;justify-content:center;z-index:99;flex-direction:column;gap:14px}
  .lockscreen input{width:260px;text-align:center}
  .empty{color:var(--muted);font-size:13px;padding:14px 0;text-align:center}
  .toast{position:fixed;bottom:20px;right:20px;background:var(--panel2);border:1px solid var(--border);padding:12px 18px;border-radius:10px;font-size:13px;z-index:200;box-shadow:0 8px 24px rgba(0,0,0,.4)}
</style>
</head>
<body>

<div id="lock" class="lockscreen">
  <div class="brand"><div class="logo">💎</div><div><h1>Sadik Futures Bot</h1><p>Panel şifresi</p></div></div>
  <input id="sifreInput" type="password" placeholder="Şifre">
  <button class="btn-blue" onclick="girisYap()" style="width:260px">Giriş</button>
</div>

<div id="app" style="display:none">
<header>
  <div class="brand">
    <div class="logo">🤖</div>
    <div><h1>Sadik Futures Bot</h1><p>Manuel Onay Paneli</p></div>
  </div>
  <div class="row" style="align-items:center">
    <span class="status-chip" id="otomatikRozet"><span class="dot"></span> <span id="otomatikMetin">—</span></span>
    <span class="updated" id="sonGuncelleme"></span>
  </div>
</header>

<div class="grid">
  <!-- SOL SÜTUN -->
  <div>
    <div class="card">
      <h2>⚡ Hızlı Kontrol</h2>
      <div class="row" style="margin-bottom:8px">
        <button class="btn-green" style="flex:1" onclick="aksiyon('baslat')">▶️ Otomatik Girişi Başlat</button>
        <button class="btn-red" style="flex:1" onclick="aksiyon('durdur')">🛑 Otomatik Girişi Durdur</button>
      </div>
      <div class="row">
        <button class="btn-purple" style="flex:1" onclick="taramaBaslat()">🔍 Tara</button>
        <button class="btn-orange" style="flex:1" onclick="kapatHepsiOnay()">🚨 Tümünü Kapat</button>
      </div>
    </div>

    <div class="card">
      <h2>📈 Aktif Pozisyonlar / Bekleyen Emirler <span class="muted" id="pozSayi" style="margin-left:auto;font-weight:400"></span></h2>
      <table><thead><tr><th>Coin</th><th>Yön</th><th>Giriş</th><th>Şimdi</th><th>PnL</th><th>SL/TP</th><th></th></tr></thead>
      <tbody id="pozTablo"><tr><td colspan="7" class="empty">Yükleniyor...</td></tr></tbody></table>
    </div>

    <div class="card">
      <h2>📋 Son İşlemler</h2>
      <table><thead><tr><th>Zaman</th><th>Coin</th><th>PnL</th><th>Sebep</th></tr></thead>
      <tbody id="gecmisTablo"><tr><td colspan="4" class="empty">Yükleniyor...</td></tr></tbody></table>
    </div>
  </div>

  <!-- ORTA SÜTUN -->
  <div>
    <div class="card">
      <h2>💼 Bot Durumu</h2>
      <div class="statline"><span>Bitget API</span><span id="stBitget">—</span></div>
      <div class="statline"><span>Telegram</span><span id="stTelegram">—</span></div>
      <div class="statline"><span>Bakiye</span><span id="stBakiye">—</span></div>
      <div class="statline"><span>Açık Pozisyon</span><span id="stAcik">—</span></div>
      <div class="statline"><span>Bekleyen Emir</span><span id="stBekleyen">—</span></div>
    </div>

    <div class="card">
      <h2>📊 Canlı Grafik</h2>
      <div class="row" style="margin-bottom:10px">
        <select id="grafikSembol" onchange="grafikYukle()" style="flex:1"></select>
        <button class="tf-btn active" data-tf="15m" onclick="tfSec('15m')">15m</button>
        <button class="tf-btn" data-tf="1h" onclick="tfSec('1h')">1S</button>
        <button class="tf-btn" data-tf="4h" onclick="tfSec('4h')">4S</button>
      </div>
      <div id="chart"></div>
    </div>

    <div class="card">
      <h2>✍️ Manuel Aç (Limit Emir)</h2>
      <div class="field"><label>Sembol (örn. PUMP)</label><input id="acSembol" placeholder="PUMP"></div>
      <div class="row">
        <div class="field" style="flex:1"><label>Yön</label>
          <select id="acYon"><option value="long">Long</option><option value="short">Short</option></select></div>
        <div class="field" style="flex:1"><label>Marjin ($)</label><input id="acMarjin" value="5" type="number"></div>
      </div>
      <div class="row">
        <div class="field" style="flex:1"><label>Giriş</label><input id="acGiris" type="number" step="any"></div>
        <div class="field" style="flex:1"><label>SL</label><input id="acSl" type="number" step="any"></div>
        <div class="field" style="flex:1"><label>TP</label><input id="acTp" type="number" step="any"></div>
      </div>
      <button class="btn-blue" style="width:100%" onclick="manuelAc()">Limit Emri Gönder</button>
    </div>
  </div>

  <!-- SAĞ SÜTUN -->
  <div>
    <div class="card">
      <h2>🔎 Piyasa Taraması <span class="muted" id="taramaZaman" style="margin-left:auto;font-weight:400"></span></h2>
      <div id="btcBaglam" class="statline" style="border:0"></div>
      <div id="taramaListe"><div class="empty">Henüz tarama yapılmadı — "🔍 Tara" butonuna bas.</div></div>
    </div>
  </div>
</div>
</div>

<script>
let SIFRE = localStorage.getItem("panel_sifre") || "";
let chart, candleSeries, aktifTf = "15m";

function girisYap(){
  SIFRE = document.getElementById("sifreInput").value;
  localStorage.setItem("panel_sifre", SIFRE);
  baslat();
}
async function api(path, opts={}){
  opts.headers = Object.assign({"X-Panel-Sifre": SIFRE, "Content-Type":"application/json"}, opts.headers||{});
  const r = await fetch(path, opts);
  if(r.status === 401){ document.getElementById("lock").style.display="flex"; document.getElementById("app").style.display="none"; throw new Error("yetkisiz"); }
  return r.json();
}
function toast(msg){
  const t = document.createElement("div"); t.className="toast"; t.textContent=msg;
  document.body.appendChild(t); setTimeout(()=>t.remove(), 3500);
}
async function aksiyon(ad, ekstra={}){
  try{
    const sonuc = await api("/api/action", {method:"POST", body: JSON.stringify(Object.assign({aksiyon: ad}, ekstra))});
    toast(sonuc.mesaj || (sonuc.tamam ? "Tamam" : (sonuc.hata||"Hata")));
    yenile();
  }catch(e){}
}
function kapatHepsiOnay(){
  if(confirm("Tüm açık pozisyonlar piyasa fiyatından kapatılacak, bekleyen emirler iptal edilecek. Emin misin?"))
    aksiyon("kapat_hepsi");
}
async function taramaBaslat(){
  await api("/api/tara", {method:"POST"});
  document.getElementById("taramaListe").innerHTML = '<div class="empty">Taranıyor...</div>';
  taramaPoll();
}
async function taramaPoll(){
  const d = await api("/api/tara");
  if(d.calisiyor){ setTimeout(taramaPoll, 2000); return; }
  taramaGoster(d);
}
function taramaGoster(d){
  document.getElementById("taramaZaman").textContent = d.son_guncelleme || "";
  if(d.btc && d.btc.y4)
    document.getElementById("btcBaglam").innerHTML = `<span>BTC 4S/1S</span><span>${d.btc.y4} (${d.btc.r4}) / ${d.btc.y1} (${d.btc.r1})</span>`;
  const kutu = document.getElementById("taramaListe");
  if(!d.sonuc || !d.sonuc.length){ kutu.innerHTML = '<div class="empty">Temiz bir kurulum bulunamadı.</div>'; return; }
  kutu.innerHTML = d.sonuc.map(a => `
    <div class="card" style="background:#0d1729;margin-bottom:10px;padding:12px">
      <div class="row" style="justify-content:space-between;align-items:center">
        <b>${a.symbol.split('/')[0]} ${a.yon==='long'?'🟢 UZUN':'🔴 KISA'}</b>
        <span class="muted">R/R ${a.rr}</span>
      </div>
      <div class="muted" style="font-size:12px;margin:6px 0">4S ${a.y4} (RSI ${a.r4}) · 1S ${a.y1} (RSI ${a.r1})</div>
      <div style="font-size:12.5px">Giriş ${a.fiyat} · SL ${a.sl} · TP ${a.tp}</div>
      <button class="btn-blue" style="margin-top:8px;width:100%" onclick='doldurVeAc(${JSON.stringify(a)})'>Bu Adayı Aç</button>
    </div>`).join("");
}
function doldurVeAc(a){
  document.getElementById("acSembol").value = a.symbol.split("/")[0];
  document.getElementById("acYon").value = a.yon;
  document.getElementById("acGiris").value = a.fiyat;
  document.getElementById("acSl").value = a.sl;
  document.getElementById("acTp").value = a.tp;
  window.scrollTo({top:400, behavior:"smooth"});
}
async function manuelAc(){
  const sembol = document.getElementById("acSembol").value.trim().toUpperCase();
  const body = {
    symbol: sembol.includes("/") ? sembol : sembol + "/USDT:USDT",
    yon: document.getElementById("acYon").value,
    giris: document.getElementById("acGiris").value,
    sl: document.getElementById("acSl").value,
    tp: document.getElementById("acTp").value,
    marjin: document.getElementById("acMarjin").value,
  };
  aksiyon("ac", body);
}
async function pozKapat(symbol){ if(confirm(symbol+" kapatılsın mı?")) aksiyon("kapat", {symbol}); }

async function durumYukle(){
  const d = await api("/api/status");
  const rozet = document.getElementById("otomatikRozet");
  rozet.className = "status-chip" + (d.otomatik_giris ? "" : " off");
  document.getElementById("otomatikMetin").textContent = d.otomatik_giris ? "OTOMATİK GİRİŞ AÇIK" : "MANUEL MOD";
  document.getElementById("sonGuncelleme").textContent = "Son güncelleme: " + d.son_guncelleme;
  document.getElementById("stBitget").innerHTML = d.bitget_bagli ? '<span class="g">Bağlı</span>' : '<span class="r">Bağlı değil</span>';
  document.getElementById("stTelegram").innerHTML = d.telegram_bagli ? '<span class="g">Bağlı</span>' : '<span class="r">Bağlı değil</span>';
  document.getElementById("stBakiye").textContent = d.bakiye != null ? "$"+d.bakiye.toFixed(2) : "—";
  document.getElementById("stAcik").textContent = d.acik_sayi + "/" + d.max_pos;
  document.getElementById("stBekleyen").textContent = d.bekleyen_sayi;
}
async function pozYukle(){
  const liste = await api("/api/positions");
  document.getElementById("pozSayi").textContent = liste.length + " kayıt";
  const tablo = document.getElementById("pozTablo");
  if(!liste.length){ tablo.innerHTML = '<tr><td colspan="7" class="empty">Açık pozisyon yok.</td></tr>'; }
  else tablo.innerHTML = liste.map(p => `
    <tr>
      <td><b>${p.symbol.split('/')[0]}</b></td>
      <td><span class="pill ${p.durum==='bekleyen'?'bekleyen':p.yon}">${p.durum==='bekleyen' ? 'BEKLİYOR' : p.yon.toUpperCase()}</span></td>
      <td>${p.entry}</td>
      <td>${p.simdi ?? '—'}</td>
      <td class="${p.pnl_usdt>=0?'g':'r'}">${p.pnl_usdt!=null ? (p.pnl_usdt>=0?'+':'')+p.pnl_usdt+'$ ('+p.pnl_pct+'%)' : '—'}</td>
      <td class="muted">${p.sl} / ${p.tp}</td>
      <td><button class="btn-outline" onclick="pozKapat('${p.symbol}')">Kapat</button></td>
    </tr>`).join("");
  try{
    const semboller = [...new Set(liste.map(p=>p.symbol))];
    const sel = document.getElementById("grafikSembol");
    if(sel.dataset.dolu !== semboller.join(",")){
      sel.innerHTML = (semboller.length?semboller:["BTC/USDT:USDT"]).map(s=>`<option value="${s}">${s.split('/')[0]}</option>`).join("");
      sel.dataset.dolu = semboller.join(",");
      grafikYukle();
    }
  }catch(e){ console.warn("grafik sembol listesi güncellenemedi", e); }
}
async function gecmisYukle(){
  const liste = await api("/api/history?limit=10");
  const tablo = document.getElementById("gecmisTablo");
  if(!liste.length){ tablo.innerHTML = '<tr><td colspan="4" class="empty">Henüz kapanan işlem yok.</td></tr>'; return; }
  tablo.innerHTML = liste.map(t => `
    <tr><td class="muted">${(t.zaman||'').split(' ')[1]||''}</td><td>${(t.symbol||'').split('/')[0]}</td>
    <td class="${t.pnl>=0?'g':'r'}">${t.pnl>=0?'+':''}${t.pnl.toFixed(2)}$</td><td class="muted">${t.not||''}</td></tr>`).join("");
}
function tfSec(tf){
  aktifTf = tf;
  document.querySelectorAll(".tf-btn").forEach(b=>b.classList.toggle("active", b.dataset.tf===tf));
  grafikYukle();
}
async function grafikYukle(){
  if(!candleSeries) return;   // grafik kütüphanesi yüklenemediyse sessizce atla
  try{
    const sembol = document.getElementById("grafikSembol").value || "BTC/USDT:USDT";
    const veri = await api(`/api/ohlcv?symbol=${encodeURIComponent(sembol)}&tf=${aktifTf}&limit=150`);
    if(!Array.isArray(veri)) return;
    candleSeries.setData(veri.map(v=>({time:v.time, open:v.open, high:v.high, low:v.low, close:v.close})));
  }catch(e){ console.warn("grafik verisi yüklenemedi", e); }
}
function grafikKur(){
  try{
    if(typeof LightweightCharts === "undefined"){
      document.getElementById("chart").innerHTML = '<div class="empty">Grafik kütüphanesi yüklenemedi (ağ engeli olabilir) - diğer bölümler normal çalışır.</div>';
      return;
    }
    chart = LightweightCharts.createChart(document.getElementById("chart"), {
      layout:{background:{color:"transparent"}, textColor:"#8695b3"},
      grid:{vertLines:{color:"#16203a"}, horzLines:{color:"#16203a"}},
      timeScale:{timeVisible:true}, height:280,
    });
    candleSeries = chart.addCandlestickSeries({upColor:"#22c55e", downColor:"#ef4444", borderVisible:false, wickUpColor:"#22c55e", wickDownColor:"#ef4444"});
    new ResizeObserver(()=>chart.applyOptions({width:document.getElementById("chart").clientWidth})).observe(document.getElementById("chart"));
  }catch(e){
    console.warn("grafik kurulamadı", e);
    document.getElementById("chart").innerHTML = '<div class="empty">Grafik yüklenemedi - diğer bölümler normal çalışır.</div>';
  }
}
async function yenile(){
  const sonuclar = await Promise.allSettled([durumYukle(), pozYukle(), gecmisYukle()]);
  sonuclar.forEach((r,i)=>{ if(r.status==="rejected") console.warn(["durum","pozisyonlar","gecmis"][i]+" yüklenemedi:", r.reason); });
}
async function baslat(){
  try{
    await durumYukle();
  }catch(e){ return; /* şifre yanlış ya da bağlantı yok - kilit ekranında kal */ }
  document.getElementById("lock").style.display="none";
  document.getElementById("app").style.display="block";
  try{ grafikKur(); }catch(e){ console.warn("grafikKur hata verdi", e); }
  yenile();
  try{ taramaPoll(); }catch(e){ console.warn("tarama başlatılamadı", e); }
  setInterval(yenile, 15000);
}
if(SIFRE) baslat(); 
</script>
</body>
</html>"""


# ════════════════════════════════════════════
# v6.2: WEB PANELİ - Flask API + gömülü tek-sayfa arayüz
# ════════════════════════════════════════════
web_app = Flask("panel")
_web_tarama_durum = {"calisiyor": False, "sonuc": [], "btc": {}, "son_guncelleme": None}
_web_tarama_kilit = threading.Lock()


def _panel_sifre_dogru():
    if not WEB_PANEL_SIFRE:
        return False
    girilen = request.headers.get("X-Panel-Sifre") or request.args.get("sifre") or ""
    return girilen == WEB_PANEL_SIFRE


@web_app.before_request
def _panel_yetki_kontrol():
    if request.path == "/":
        return None
    if not _panel_sifre_dogru():
        return jsonify({"hata": "Yetkisiz - şifre eksik/hatalı"}), 401


@web_app.route("/api/status")
def api_status():
    bakiye = gercek_bakiye_al()
    with state_lock:
        acik_sayi = len(trade_state)
    with manuel_kilit:
        bekleyen_sayi = len(manuel_limit_emirler)
    return jsonify({
        "bakiye": bakiye, "otomatik_giris": OTOMATIK_GIRIS_AKTIF, "acik_sayi": acik_sayi,
        "max_pos": MAX_POS, "bekleyen_sayi": bekleyen_sayi,
        "bitget_bagli": bakiye is not None, "telegram_bagli": bot is not None,
        "son_guncelleme": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    })


@web_app.route("/api/positions")
def api_positions():
    with state_lock:
        durumlar = dict(trade_state)
    with manuel_kilit:
        bekleyenler = dict(manuel_limit_emirler)
    sonuc = []
    for sym, d in durumlar.items():
        try:
            simdi = safe(exchange.fetch_ticker(sym).get("last"))
        except Exception:
            simdi = d["entry"]
        long_mu = d["yon"] == "long"
        pnl_pct = (simdi / d["entry"] - 1) * 100 if long_mu else (d["entry"] / simdi - 1) * 100
        pnl_usdt = pnl_pct / 100 * d.get("notional", 0)
        sonuc.append({"symbol": sym, "yon": d["yon"], "entry": d["entry"], "simdi": simdi,
                       "pnl_pct": round(pnl_pct, 2), "pnl_usdt": round(pnl_usdt, 2),
                       "sl": d["sl"], "tp": d["tp"], "trailing_aktif": d.get("trailing_aktif", False),
                       "acilis_modu": d.get("acilis_modu", "?"), "durum": "acik"})
    for sym, k in bekleyenler.items():
        sonuc.append({"symbol": sym, "yon": k["yon"], "entry": k["entry_hedef"], "simdi": None,
                       "pnl_pct": None, "pnl_usdt": None, "sl": k["sl"], "tp": k["tp"],
                       "trailing_aktif": False, "acilis_modu": "bekleyen", "durum": "bekleyen"})
    return jsonify(sonuc)


@web_app.route("/api/history")
def api_history():
    limit = int(request.args.get("limit", 20))
    with log_lock:
        gecmis = list(trade_log)
    return jsonify(list(reversed(gecmis))[:limit])


@web_app.route("/api/ohlcv")
def api_ohlcv():
    sym = request.args.get("symbol", "BTC/USDT:USDT")
    tf = request.args.get("tf", "15m")
    limit = min(int(request.args.get("limit", 100)), 300)
    try:
        veri = exchange.fetch_ohlcv(sym, tf, limit=limit)
    except Exception as e:
        return jsonify({"hata": str(e)}), 500
    return jsonify([{"time": c[0] // 1000, "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5]} for c in veri])


def _web_tarama_arkaplan():
    with _web_tarama_kilit:
        if _web_tarama_durum["calisiyor"]:
            return
        _web_tarama_durum["calisiyor"] = True
    try:
        bulunanlar, btc_baglam = manuel_tarama_yap()
        with _web_tarama_kilit:
            _web_tarama_durum["sonuc"] = bulunanlar
            _web_tarama_durum["btc"] = btc_baglam
            _web_tarama_durum["son_guncelleme"] = time.strftime("%H:%M:%S UTC", time.gmtime())
    except Exception as e:
        log.warning(f"[WEB_TARAMA] {e}")
    finally:
        with _web_tarama_kilit:
            _web_tarama_durum["calisiyor"] = False


@web_app.route("/api/tara", methods=["GET", "POST"])
def api_tara():
    if request.method == "POST":
        threading.Thread(target=_web_tarama_arkaplan, daemon=True).start()
        return jsonify({"basladi": True})
    with _web_tarama_kilit:
        return jsonify(dict(_web_tarama_durum))


@web_app.route("/api/action", methods=["POST"])
def api_action():
    veri = request.get_json(force=True, silent=True) or {}
    aksiyon = veri.get("aksiyon")
    global OTOMATIK_GIRIS_AKTIF
    if aksiyon == "durdur":
        OTOMATIK_GIRIS_AKTIF = False
        return jsonify({"tamam": True, "otomatik_giris": False})
    if aksiyon == "baslat":
        OTOMATIK_GIRIS_AKTIF = True
        return jsonify({"tamam": True, "otomatik_giris": True})
    if aksiyon == "kapat_hepsi":
        kapatilan, iptal_edilen = tum_pozisyonlari_kapat()
        return jsonify({"tamam": True, "kapatilan": kapatilan, "iptal_edilen": iptal_edilen})
    if aksiyon == "kapat":
        sym = veri.get("symbol")
        with state_lock:
            var_mi = sym in trade_state
        if var_mi:
            basarili, mesaj = gercek_pozisyon_kapat(sym, "manuel_web_kapat")
            return jsonify({"tamam": basarili, "mesaj": mesaj}), (200 if basarili else 500)
        if manuel_limit_iptal(sym, "web panelden iptal"):
            return jsonify({"tamam": True})
        return jsonify({"tamam": False, "hata": "Bulunamadı"}), 404
    if aksiyon == "ac":
        try:
            aday = {"symbol": veri["symbol"], "yon": veri["yon"], "fiyat": float(veri["giris"])}
            sl, tp = float(veri["sl"]), float(veri["tp"])
            marjin = float(veri["marjin"]) if veri.get("marjin") else None
        except Exception as e:
            return jsonify({"tamam": False, "hata": f"Eksik/hatalı parametre: {e}"}), 400
        basarili, mesaj = manuel_limit_ac(aday, sl, tp, marjin)
        return jsonify({"tamam": basarili, "mesaj": mesaj}), (200 if basarili else 400)
    return jsonify({"tamam": False, "hata": "Bilinmeyen aksiyon"}), 400


@web_app.route("/")
def api_index():
    return Response(PANEL_HTML, mimetype="text/html")


def web_panel_baslat():
    if not WEB_PANEL_AKTIF:
        log.info("[WEB_PANEL] WEB_PANEL_AKTIF=false, web paneli başlatılmıyor.")
        return
    if not WEB_PANEL_SIFRE:
        log.warning("[WEB_PANEL] WEB_PANEL_SIFRE ayarlanmamış - panel API'si TÜM istekleri reddedecek. "
                    "Railway'de WEB_PANEL_SIFRE değişkenini ekle.")
    try:
        web_app.run(host="0.0.0.0", port=WEB_PANEL_PORT, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        log.error(f"[WEB_PANEL] başlatılamadı: {e}")


def manuel_limit_loop():
    """Bekleyen manuel limit emirlerinin doluşunu izler; dolunca SL/TP kurar
    ve trade_state'e 'manuel' modunda ekler (iz sürme dahil)."""
    while True:
        try:
            with manuel_kilit:
                semboller = list(manuel_limit_emirler.keys())
            for sym in semboller:
                with manuel_kilit:
                    kayit = manuel_limit_emirler.get(sym)
                if not kayit:
                    continue
                if time.time() - kayit["konulma_zamani"] > MANUEL_LIMIT_TIMEOUT_SN:
                    manuel_limit_iptal(sym, "zaman aşımı")
                    continue
                try:
                    durum_emir = exchange.fetch_order(kayit["order_id"], sym)
                except Exception as e:
                    log.warning(f"[MANUEL_FETCH] {sym}: {e}")
                    continue
                if durum_emir.get("status") not in ("closed", "filled"):
                    continue
                # Doldu: gerçek giriş fiyatını al, SL/TP kur, state'e yaz
                long_mu = kayit["yon"] == "long"
                entry = safe(durum_emir.get("average")) or kayit["entry_hedef"]
                kapanis_yonu = "sell" if long_mu else "buy"
                sl_fiyat = float(exchange.price_to_precision(sym, kayit["sl"]))
                sl_emir_id = None
                for _ in range(3):
                    try:
                        sl_emri = exchange.create_order(sym, "market", kapanis_yonu, kayit["qty"], None,
                                                         {"reduceOnly": True, "stopLossPrice": sl_fiyat})
                        sl_emir_id = sl_emri.get("id")
                        if sl_emir_id:
                            break
                    except Exception as e:
                        log.warning(f"[MANUEL_SL] {sym}: {e}")
                    time.sleep(0.5)
                if not sl_emir_id:
                    tg(f"🚨 {sym} manuel işlemde SL kurulamadı, güvenlik amaçlı kapatılıyor.")
                    try:
                        exchange.create_market_order(sym, kapanis_yonu, kayit["qty"], params={"reduceOnly": True})
                    except Exception:
                        pass
                    with manuel_kilit:
                        manuel_limit_emirler.pop(sym, None)
                    durumu_diske_yaz()
                    continue
                with state_lock:
                    trade_state[sym] = {
                        "entry": entry, "sl": kayit["sl"], "tp": kayit["tp"], "sl_emir_id": sl_emir_id,
                        "yon": kayit["yon"], "qty": kayit["qty"], "r_risk": abs(entry - kayit["sl"]),
                        "acilis_zamani": time.time(), "1d": "-", "4h": kayit.get("4h", "-"), "1h": kayit.get("1h", "-"),
                        "notional": kayit["qty"] * entry, "son_trend_kontrol": 0, "ters_trend_sayisi": 0,
                        "kismi_ters_sayisi": 0, "kismi_alindi": False, "acilis_modu": "manuel",
                        "erken_kontrol_yapildi": False, "en_yuksek_fiyat": entry, "trailing_aktif": False,
                    }
                with manuel_kilit:
                    manuel_limit_emirler.pop(sym, None)
                durumu_diske_yaz()
                kaldirac_satiri = pozisyon_kaldirac_satiri(sym, long_mu, kayit["sl"], kayit.get("lev", LEV), kayit.get("mod"))
                tg(f"✅ MANUEL İŞLEM AÇILDI: {sym} {'🟢 LONG' if long_mu else '🔴 SHORT'}\n"
                   f"Giriş: {entry:.8g} | SL: {kayit['sl']:.8g} | TP: {kayit['tp']:.8g}\n"
                   f"{kaldirac_satiri}"
                   f"⚡ İz sürme kâr %{YUKSELEN_TRAILING_AKTIVASYON_PCT*100:.1f}'e ulaşınca otomatik devreye girer.")
        except Exception as e:
            log.error(f"[MANUEL_LIMIT_LOOP] {e}")
        time.sleep(10)


def gercek_pozisyon_ac(sinyal):
    sym = sinyal["symbol"]

    if coin_bloke_mi(sym):
        log.info(f"[COIN_BLOKE] {sym} engelli, açılış atlanıyor")
        return

    with state_lock:
        if sym in trade_state or sym in acilis_rezervasyonlari:
            return
        if len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
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

    # v5.8: yalnızca YUKSELEN sinyallerine uygulanan iki koruma (ikisi de cooldown UYGULAMAZ:
    # aynı sinyal mumu içinde sonraki taramada koşullar düzelirse giriş yapılabilir).
    if sinyal.get("swing_nokta", 1) is None and aktif_strateji_modu() == "yukselen":
        _mum_ts = sinyal.get("mum_ts")
        if AYNI_MUM_MAX_GIRIS > 0 and _mum_ts is not None and ayni_mum_dolu_mu(_mum_ts):
            if engel_bir_kez((sym, _mum_ts, "mum")):
                log.info(f"[AYNI_MUM_SINIRI] {sym} atlandı: bu 15dk mumundan zaten {AYNI_MUM_MAX_GIRIS} pozisyon açıldı")
            return
        _hedef = sinyal.get("entry", 0)
        if KOVALAMA_KORUMA_AKTIF and _hedef > 0:
            try:
                _simdi = safe(exchange.fetch_ticker(sym).get("last"))
            except Exception as e:
                log.warning(f"[KOVALAMA_FIYAT] {sym}: {e}")
                _simdi = 0
            if _simdi > 0:
                _uzun = sinyal.get("yon", "long") == "long"
                _kovalama = ((_simdi - _hedef) / _hedef * 100) if _uzun else ((_hedef - _simdi) / _hedef * 100)
                if _kovalama > KOVALAMA_MAX_PCT:
                    if engel_bir_kez((sym, _mum_ts, "kovalama")):
                        surtunme_kaydet("engel", sym, _kovalama)
                        log.info(f"[KOVALAMA_ENGEL] {sym} atlandı: fiyat sinyal kapanışından %{_kovalama:.2f} pahalı (limit %{KOVALAMA_MAX_PCT})")
                    return

    bakiye = gercek_bakiye_al()
    if bakiye is None or bakiye <= 0:
        tg(f"⚠️ {sym} atlandı — bakiye alınamadı")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    yon = sinyal.get("yon", "long")
    long_mu = (yon == "long")
    entry_hedef = sinyal["entry"]
    swing_nokta = sinyal["swing_nokta"]

    if swing_nokta is None:
        # v4.0: yükselen-coin modu - swing noktası kavramı yok, sabit
        # taban SL yüzdesi kullanılır (backtest'te doğrulanmış oran).
        # Bu YALNIZCA GEÇİCİ bir değer - giriş fiyatı netleştikten sonra aşağıda
        # YUKSELEN_SL_PCT (yüzdesel) ile DEĞİŞTİRİLİR (v4.9'dan beri sabit dolar SL yok).
        sl_mesafe = MIN_SL_PCT
        sl = entry_hedef * (1 - sl_mesafe) if long_mu else entry_hedef * (1 + sl_mesafe)
    elif long_mu:
        sl = swing_nokta * (1 - SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT_TAVAN, (entry_hedef - sl) / entry_hedef))
        sl = entry_hedef * (1 - sl_mesafe)
    else:
        sl = swing_nokta * (1 + SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT_TAVAN, (sl - entry_hedef) / entry_hedef))
        sl = entry_hedef * (1 + sl_mesafe)

    if sl_mesafe <= 0:
        acilis_basarisiz_cooldown_uygula(sym)
        return

    LEV_KULLANILAN = sembol_max_kaldirac(sym, LEV)
    marjin_kullanilan = hesapla_marjin(bakiye)
    notional = marjin_kullanilan * LEV_KULLANILAN
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

    kaldirac_ayarla(sym, LEV_KULLANILAN, long_mu)
    time.sleep(0.3)

    acilis_yonu = "buy" if long_mu else "sell"
    kapanis_yonu = "sell" if long_mu else "buy"

    try:
        exchange.create_market_order(sym, acilis_yonu, qty)
    except Exception as e:
        tg(f"⚠️ {sym} giriş emri başarısız: {e}")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    time.sleep(0.8)
    entry = entry_hedef
    gercek_giris_alindi = False
    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
        if gercek_pos and safe(gercek_pos.get("entryPrice")) > 0:
            entry = safe(gercek_pos.get("entryPrice"))
            sl = entry * (1 - sl_mesafe) if long_mu else entry * (1 + sl_mesafe)
            gercek_giris_alindi = True
    except Exception as e:
        log.warning(f"[GERCEK_POZ] {sym}: {e}")

    # v5.6: giriş kayması (sinyal fiyatı → gerçek dolum). + = bot aleyhine.
    kayma_satiri = ""
    if gercek_giris_alindi and entry_hedef > 0:
        giris_kayma_pct = ((entry - entry_hedef) / entry_hedef * 100) if long_mu else ((entry_hedef - entry) / entry_hedef * 100)
        surtunme_kaydet("giris", sym, giris_kayma_pct)
        kayma_satiri = f"Giriş kayması: %{giris_kayma_pct:+.3f} (sinyal {entry_hedef:.6f} → dolum {entry:.6f})\n"

    # ════════════════════════════════════════════
    # v4.9 KRİTİK DÜZELTME (23.09.2026, güncel gerçek veriyle backtest
    # edilip bulundu): v4.8'deki sabit dolar SL, güncel notional
    # ölçeğinde (~$48) çok küçük bir yüzdesel harekete (~%0.7) denk
    # geliyordu - gürültü seviyesinde kalıyordu. Artık YUKSELEN modunda
    # SL de YÜZDESEL (YUKSELEN_SL_PCT, varsayılan %3) - risk/ödül oranı
    # hâlâ TP ile sabit (ikisi de aynı yüzde), ama artık anlamlı bir
    # gerçek harekete karşılık geliyor.
    if aktif_strateji_modu() == "yukselen":
        sl_mesafe = YUKSELEN_SL_PCT
        sl = entry * (1 - sl_mesafe) if long_mu else entry * (1 + sl_mesafe)

    r_risk = abs(entry - sl)
    # v4.9 GÜNCELLEME: YUKSELEN modunda TP de YÜZDESEL (YUKSELEN_HEDEF_PCT,
    # varsayılan %3) - backtest'te bu, "mümkün olduğunca hızlı ama hâlâ
    # kârlı" nokta olarak doğrulandı (%2 altı net zararlı, %3+ net kârlı).
    # v5.1 GÜNCELLEME (kullanıcı gözlemiyle bulundu - "0.80 zaten garanti,
    # neden %3'te kesiyoruz"): Backtest'te TP tavanı VARKEN ve YOKKEN net
    # sonuç TAMAMEN AYNI çıktı (519.03$, kuruşuna kadar) - çünkü iz sürme
    # (aktivasyon %2.5, dar %0.5 pay) zaten fiyatı %3'e ulaşmadan
    # yakalıyordu, tavan hiç fiili bir etki yaratmıyordu. Tavanı kaldırmak
    # HİÇBİR ŞEY KAYBETTİRMİYOR, ama büyük hareketler geldiğinde (backtest'te
    # LYN %29.5, RARE %17.7, CLANKER %15.7 gibi örnekler görüldü) tam
    # yakalanabiliyor - iz sürme SL'i o büyük hareket boyunca da yükselmeye
    # devam ediyor. YUKSELEN_TP_TAVAN_AKTIF=false (varsayılan) ile tavan
    # kapalı; true yapılırsa eski %3 sabit tavan davranışına dönülebilir.
    if aktif_strateji_modu() == "yukselen":
        if YUKSELEN_TP_TAVAN_AKTIF:
            tp = entry * (1 + YUKSELEN_HEDEF_PCT) if long_mu else entry * (1 - YUKSELEN_HEDEF_PCT)
        else:
            tp = entry * (1 + 1.0) if long_mu else entry * (1 - 0.5)  # pratikte ulaşılamaz tavan
    else:
        tp = entry * (1 + HIZLI_HEDEF_PCT) if long_mu else entry * (1 - HIZLI_HEDEF_PCT)

    sl_emir_id = None
    sl_fiyat = float(exchange.price_to_precision(sym, sl))
    for deneme in range(3):
        try:
            sl_emri = exchange.create_order(sym, "market", kapanis_yonu, qty, None,
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
            exchange.create_market_order(sym, kapanis_yonu, qty, params={"reduceOnly": True})
        except Exception:
            pass
        acilis_basarisiz_cooldown_uygula(sym)
        return

    with state_lock:
        trade_state[sym] = {
            "entry": entry, "sl": sl, "tp": tp, "sl_emir_id": sl_emir_id, "yon": yon, "qty": qty,
            "r_risk": r_risk, "acilis_zamani": time.time(),
            "1d": sinyal["1d"], "4h": sinyal["4h"], "1h": sinyal["1h"], "notional": notional,
            "son_trend_kontrol": 0, "ters_trend_sayisi": 0, "kismi_ters_sayisi": 0,
            "kismi_alindi": False, "acilis_modu": aktif_strateji_modu(),
            "erken_kontrol_yapildi": False,
            "en_yuksek_fiyat": entry, "trailing_aktif": False,
        }
    durumu_diske_yaz()
    if swing_nokta is None and sinyal.get("mum_ts") is not None:
        ayni_mum_kaydet(sinyal["mum_ts"])        # v5.8: aynı mumdan kaç giriş açıldı

    yon_emoji = "🟢 LONG" if long_mu else "🔴 SHORT"
    mod_simdi = aktif_strateji_modu()
    if mod_simdi == "yukselen":
        if YUKSELEN_TP_TAVAN_AKTIF:
            tp_aciklama = f"TP:{tp:.6f} (%{YUKSELEN_HEDEF_PCT*100:.1f} sabit)"
        else:
            tp_aciklama = "TP: yok (iz sürme)"
        hedef_satiri = (f"⚡ İZ SÜRME: kâr %{YUKSELEN_TRAILING_AKTIVASYON_PCT*100:.1f}'e ulaşınca SL zirveden "
                        f"%{YUKSELEN_TRAILING_PAYI_PCT*100:.1f} geriden takip eder\n")
    else:
        tp_aciklama = f"TP:{tp:.6f} (%{HIZLI_HEDEF_PCT*100:.1f} sabit)"
        hedef_satiri = "⚡ SABİT HEDEF: değer değmez HEMEN kapanır, iz sürme yok, bekleme yok\n"
    tg(f"📈 GERÇEK POZİSYON ({mod_simdi.upper()}): {sym} {yon_emoji}\n"
       f"Giriş≈{entry:.6f} | SL:{sl_fiyat:.6f} (%{sl_mesafe*100:.1f}) | {tp_aciklama}\n"
       f"{kayma_satiri}"
       f"1D:{sinyal['1d']} | 4H:{sinyal['4h']} | 1H:{sinyal['1h']}\n"
       f"✅ Hacim teyidi geçti | ✅ Pump filtresi geçti | ✅ Zirveden mesafe filtresi geçti\n"
       f"{hedef_satiri}"
       f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Marjin: ${marjin_kullanilan:.2f} "
       f"(bileşik büyüme: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i, taban ${MARJIN_TABAN_USDT:.2f})")


def kismi_kar_al(sym, durum):
    """v3.7 YENİ: pozisyonun KISMI_KAR_ORANI kadarını piyasadan kapatır
    (o kâr garanti altına alınır), kalan kısmın SL'i girişe (breakeven +
    komisyon payı) çekilir. Orijinal SL emri iptal edilip yenisi
    yerleştirilir. Herhangi bir adımda hata olursa, pozisyon eski haliyle
    (tam miktar, eski SL) güvenli şekilde bırakılır - yarım işlem riski
    yok."""
    try:
        pozlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
        if not gercek_pos:
            return False

        toplam_qty = safe(gercek_pos.get("contracts"))
        entry = durum["entry"]
        long_mu = durum.get("yon", "long") == "long"
        kapanis_yonu = "sell" if long_mu else "buy"

        kapanacak_qty = float(exchange.amount_to_precision(sym, toplam_qty * KISMI_KAR_ORANI))
        if kapanacak_qty <= 0:
            return False

        kapama_emri = exchange.create_market_order(sym, kapanis_yonu, kapanacak_qty, params={"reduceOnly": True})
        time.sleep(0.8)
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
                cikis_fiyat = entry

        kismi_pnl = (cikis_fiyat - entry) * kapanacak_qty if long_mu else (entry - cikis_fiyat) * kapanacak_qty
        trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat, "pnl": kismi_pnl,
                           "yon": durum.get("yon", "long"), "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                           "not": "kismi_kar_alma", "1d": durum.get("1d"), "4h": durum.get("4h"),
                           "1h": durum.get("1h")})

        # Kalan miktarın SL'ini breakeven'e (+ komisyon payı) çek
        kalan_qty = float(exchange.amount_to_precision(sym, toplam_qty - kapanacak_qty))

        if kalan_qty <= 0:
            # Yuvarlama sonucu kapatılacak miktar zaten tüm pozisyonu
            # kapsıyor demektir - pozisyon tamamen kapanmış sayılır,
            # state'ten tamamen çıkarılır (yarım/tanımsız durum bırakılmaz).
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            tg(f"🟢 {sym} KISMİ KÂR ALINDI (tam kapanış - yuvarlama): "
               f"{kapanacak_qty} kapatıldı, PnL≈{kismi_pnl:+.2f}$")
            return True

        eski_sl_id = durum.get("sl_emir_id")
        if eski_sl_id:
            try:
                exchange.cancel_order(eski_sl_id, sym)
            except Exception as e:
                log.warning(f"[KISMI_KAR_SL_IPTAL] {sym}: {e}")

        yeni_sl = entry * (1 + BREAKEVEN_KOMISYON_PAYI) if long_mu else entry * (1 - BREAKEVEN_KOMISYON_PAYI)
        yeni_sl_fiyat = float(exchange.price_to_precision(sym, yeni_sl))
        yeni_sl_id = None
        for deneme in range(3):
            try:
                sl_emri = exchange.create_order(sym, "market", kapanis_yonu, kalan_qty, None,
                                                 {"reduceOnly": True, "stopLossPrice": yeni_sl_fiyat})
                yeni_sl_id = sl_emri.get("id")
                if yeni_sl_id:
                    break
            except Exception as e:
                log.warning(f"[KISMI_KAR_SL_YENI] {sym} deneme {deneme+1}/3: {e}")
            time.sleep(0.5)

        if not yeni_sl_id:
            tg(f"🚨 {sym} kısmi kâr sonrası breakeven SL yerleştirilemedi, "
               f"güvenlik amaçlı kalan pozisyon kapatılıyor.")
            try:
                exchange.create_market_order(sym, kapanis_yonu, kalan_qty, params={"reduceOnly": True})
            except Exception:
                pass
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            return True

        with state_lock:
            if sym in trade_state:
                trade_state[sym]["kismi_alindi"] = True
                trade_state[sym]["qty"] = kalan_qty
                trade_state[sym]["sl"] = yeni_sl
                trade_state[sym]["sl_emir_id"] = yeni_sl_id
        durumu_diske_yaz()

        tg(f"🟢 {sym} KISMİ KÂR ALINDI: {kapanacak_qty} kapatıldı, PnL≈{kismi_pnl:+.2f}$\n"
           f"Kalan {kalan_qty} için SL breakeven'e çekildi ({yeni_sl:.6f}) - "
           f"kalan kısım en kötü ihtimalle nötr kapanır, tam hedef hâlâ geçerli.")
        return True
    except Exception as e:
        log.warning(f"[KISMI_KAR_HATA] {sym}: {e}")
        return False


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
            if sebep in ("sl", "erken_guvenlik_cikisi"):
                with cooldown_lock:
                    son_kapanis_zamani[sym] = time.time()
                cooldown_diske_yaz()
            if durum:
                _kapanis_kaydet_gercek_veriyle(sym, durum, sebep)
            return True, "kapatildi"

        qty = safe(gercek_pos.get("contracts"))
        entry_fiyat = safe(gercek_pos.get("entryPrice"))
        yon_kayitli = (durum or {}).get("yon", "long")
        long_mu = (yon_kayitli == "long")
        kapanis_yonu = "sell" if long_mu else "buy"

        if durum and durum.get("sl_emir_id"):
            try:
                exchange.cancel_order(durum["sl_emir_id"], sym)
            except Exception:
                pass

        kapama_emri = exchange.create_market_order(sym, kapanis_yonu, qty, params={"reduceOnly": True})
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

        pnl = (cikis_fiyat - entry_fiyat) * qty if long_mu else (entry_fiyat - cikis_fiyat) * qty
        trade_log_kaydet({"symbol": sym, "entry": entry_fiyat, "exit": cikis_fiyat, "pnl": pnl,
                           "yon": yon_kayitli, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                           "not": sebep, "1d": (durum or {}).get("1d"), "4h": (durum or {}).get("4h"),
                           "1h": (durum or {}).get("1h")})
        with state_lock:
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        if sebep in ("sl", "erken_guvenlik_cikisi"):
            with cooldown_lock:
                son_kapanis_zamani[sym] = time.time()
            cooldown_diske_yaz()
        tg(f"{'🟢' if pnl>=0 else '🔴'} GERÇEK kapandı: {sym} [{sebep}] PnL≈{pnl:+.2f}$")
        return True, f"✅ {sym} kapatıldı | PnL≈{pnl:+.2f}$"
    except Exception as e:
        return False, f"⚠️ {sym} kapatma hatası: {e}"


# ════════════════════════════════════════════
# v5.6: SÜRTÜNME KAYDI, GÜNLÜK ZARAR FRENİ, STOP TEŞHİSİ
# ════════════════════════════════════════════
_surtunme_kilit = threading.Lock()
_frene_bildirim = {"gun": None}


def surtunme_kaydet(tip, sym, kayma_pct):
    """tip: 'giris' ya da 'stop'. kayma_pct > 0 => bot aleyhine (daha kötü fiyattan dolum)."""
    try:
        with _surtunme_kilit:
            veri = guvenli_oku(SURTUNME_PATH, [])
            veri.append({"tip": tip, "symbol": sym, "kayma_pct": round(kayma_pct, 4),
                         "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())})
            atomik_yaz(SURTUNME_PATH, veri[-500:])
    except Exception as e:
        log.warning(f"[SURTUNME_KAYIT] {e}")


def surtunme_ozet_metni():
    veri = guvenli_oku(SURTUNME_PATH, [])
    if not veri:
        return "📏 SÜRTÜNME: henüz kayıt yok (yeni girişler/stoplar birikince dolar)."
    satirlar = ["📏 SÜRTÜNME ÖZETİ (+ = bot aleyhine, yani daha kötü fiyattan dolum)\n"]
    ort = {}
    for tip, etiket in [("giris", "Giriş (sinyal fiyatı → dolum)"), ("stop", "Stop (tetik fiyatı → dolum)")]:
        x = sorted(v["kayma_pct"] for v in veri if v.get("tip") == tip)
        if not x:
            satirlar.append(f"{etiket}: kayıt yok")
            continue
        ort[tip] = sum(x) / len(x)
        satirlar.append(f"{etiket}: n={len(x)} | ortalama %{ort[tip]:+.3f} | medyan %{x[len(x)//2]:+.3f} | en kötü %{x[-1]:+.3f}")
    eng = [v["kayma_pct"] for v in veri if v.get("tip") == "engel"]
    if eng:
        satirlar.append(f"Kovalama engeli: {len(eng)} kez girilmedi (engellenen girişlerin ortalama kayması %{sum(eng)/len(eng):+.3f})")
    if "giris" in ort:
        toplam = ort["giris"] + (ort.get("stop", 0) * 0.45)
        satirlar.append(f"\nİşlem başına tahmini ek maliyet ≈ %{toplam:.3f} (stopla biten işlem payı ~%45 varsayıldı)")
        satirlar.append("Referans: backtest'te işlem başına üstünlük ≈ %0.5-0.65 ve sürtünme 0 varsayıldı.")
        satirlar.append("Ek maliyet %0.3'ü aşarsa üstünlük büyük ölçüde erimiş demektir.")
    return "\n".join(satirlar)


def gunluk_zarar_freni_mi():
    """(fren_aktif, bugunku_gerceklesen_pnl, gun_basi_bakiye) döner. Gerçekleşen PNL trade_log'dan
    (bugün, UTC) toplanır; komisyon dahil değil, yaklaşık. /sifirlagecmis günlük sayacı da sıfırlar."""
    if not GUNLUK_ZARAR_FRENI_AKTIF:
        return False, 0.0, 0.0
    try:
        bugun = time.strftime("%Y-%m-%d", time.gmtime())
        with log_lock:
            gerceklesen = sum(t.get("pnl", 0) for t in trade_log if str(t.get("zaman", "")).startswith(bugun))
        if gerceklesen >= 0:
            return False, gerceklesen, 0.0          # kâr/nötr günde bakiye sorgusuna gerek yok
        bakiye = gercek_bakiye_al()
        if bakiye is None:
            return False, gerceklesen, 0.0
        gun_basi = bakiye - gerceklesen
        if gun_basi <= 0:
            return False, gerceklesen, gun_basi
        return gerceklesen <= -GUNLUK_ZARAR_LIMIT_PCT * gun_basi, gerceklesen, gun_basi
    except Exception as e:
        log.warning(f"[GUNLUK_FREN] {e}")
        return False, 0.0, 0.0


_mum_giris_sayaci = {}
_mum_kilit = threading.Lock()
_engel_kayitli = set()


def ayni_mum_dolu_mu(mum_ts):
    """Bu 15dk mumundan zaten AYNI_MUM_MAX_GIRIS kadar pozisyon açıldıysa True."""
    with _mum_kilit:
        return _mum_giris_sayaci.get(mum_ts, 0) >= AYNI_MUM_MAX_GIRIS


def ayni_mum_kaydet(mum_ts):
    with _mum_kilit:
        _mum_giris_sayaci[mum_ts] = _mum_giris_sayaci.get(mum_ts, 0) + 1
        for eski in sorted(_mum_giris_sayaci)[:-20]:      # sadece son 20 mumu tut
            _mum_giris_sayaci.pop(eski, None)


def engel_bir_kez(anahtar):
    """Aynı (coin, mum, tür) engelini dakikada bir tekrar loglamamak için. İlk seferde True döner."""
    if anahtar in _engel_kayitli:
        return False
    if len(_engel_kayitli) > 500:
        _engel_kayitli.clear()
    _engel_kayitli.add(anahtar)
    return True


def borsa_stoplarini_oku(sym):
    """SADECE OKUR (emir göndermez/iptal etmez). Borsadaki açık TP/SL plan emirlerini döndürür:
    [(id, tetik_fiyati, planType)]. Amaç: iz sürmede eski stop'ların değişip değişmediğini/birikip
    birikmediğini görmek. Hata olursa None."""
    try:
        emirler = exchange.fetch_open_orders(sym, None, None, {"planType": "profit_loss"})
    except Exception as e:
        log.warning(f"[STOP_TESHIS] {sym}: {e}")
        return None
    sonuc = []
    for o in emirler:
        info = o.get("info") or {}
        tetik = (o.get("triggerPrice") or o.get("stopLossPrice") or info.get("stopLossTriggerPrice")
                 or info.get("triggerPrice"))
        sonuc.append((o.get("id"), tetik, info.get("planType")))
    return sonuc


def _kapanis_kaydet_gercek_veriyle(sym, durum, sebep):
    entry = durum["entry"]
    qty = durum.get("qty", 0)
    cikis_fiyat = None
    gercek_dolum_var = False
    sl_id = durum.get("sl_emir_id")
    if sl_id:
        try:
            detay = exchange.fetch_order(sl_id, sym)
            if detay.get("status") in ("closed", "filled"):
                dolum = safe(detay.get("average")) or safe(detay.get("price"))
                if dolum > 0:
                    cikis_fiyat = dolum
                    gercek_dolum_var = True
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
                    gercek_dolum_var = True
        except Exception as e:
            log.warning(f"[ISLEM_GECMISI] {sym}: {e}")
    if not cikis_fiyat:
        try:
            t = exchange.fetch_ticker(sym)
            cikis_fiyat = safe(t["last"])
        except Exception:
            cikis_fiyat = entry

    long_mu = durum.get("yon", "long") == "long"
    pnl = (cikis_fiyat - entry) * qty if long_mu else (entry - cikis_fiyat) * qty
    trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat, "pnl": pnl,
                       "yon": durum.get("yon", "long"), "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                       "not": sebep, "1d": durum.get("1d"), "4h": durum.get("4h"), "1h": durum.get("1h")})
    stop_kayma_metni = ""
    try:
        if str(sebep).startswith("sl") and gercek_dolum_var and durum.get("sl"):
            tetik = float(durum["sl"])
            kayma = ((tetik - cikis_fiyat) / tetik * 100) if long_mu else ((cikis_fiyat - tetik) / tetik * 100)
            surtunme_kaydet("stop", sym, kayma)
            stop_kayma_metni = f" | stop kayması %{kayma:+.3f}"
    except Exception as e:
        log.warning(f"[STOP_KAYMA] {sym}: {e}")
    tg(f"{'🟢' if pnl>=0 else '🔴'} GERÇEK kapandı: {sym} [{sebep}] PnL≈{pnl:+.2f}$ (borsada önceden kapanmış){stop_kayma_metni}")


# ════════════════════════════════════════════
# PANEL
# ════════════════════════════════════════════
def panel_ozet_metni():
    with log_lock:
        gecmis = list(trade_log)
    gercek_bakiye = gercek_bakiye_al()
    bakiye_metni = f"{gercek_bakiye:,.2f}$" if gercek_bakiye is not None else "alınamadı"
    with state_lock:
        acik_sayi = len(trade_state)

    gerceklesmeyen_net = 0.0
    acik_detay = []
    with state_lock:
        durumlar = dict(trade_state)
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            entry = d["entry"]
            poz_notional = d.get("notional", NOTIONAL)
            long_mu = d.get("yon", "long") == "long"
            anlik = (guncel - entry) / entry * poz_notional if long_mu else (entry - guncel) / entry * poz_notional
            gerceklesmeyen_net += anlik
            acik_detay.append((sym, anlik))
        except Exception:
            continue

    with manuel_kilit:
        bekleyen_sayi = len(manuel_limit_emirler)
    otomatik_rozet = "🟢 AÇIK" if OTOMATIK_GIRIS_AKTIF else "⚪ KAPALI"

    satirlar = [
        "💎 <b>GHOST BOT v7.2</b>",
        f"<i>Manuel onay paneli  ·  otomatik giriş {otomatik_rozet}</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💼 Bakiye: <b>{bakiye_metni}</b>",
    ]
    if acik_sayi > 0:
        gc_emoji = "🟢" if gerceklesmeyen_net >= 0 else "🔴"
        satirlar.append(f"{gc_emoji} Açık pozisyonlarda (gerçekleşmemiş): <b>{gerceklesmeyen_net:+.2f}$</b>")
    satirlar.append(f"📈 Açık: <b>{acik_sayi}/{MAX_POS}</b>   ·   📝 Bekleyen limit emir: <b>{bekleyen_sayi}</b>")
    satirlar.append("━━━━━━━━━━━━━━━━━━━━")

    if gecmis:
        toplam = len(gecmis)
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        net = sum(t["pnl"] for t in gecmis)
        wr = len(kazanan) / toplam * 100
        net_emoji = "🟢" if net >= 0 else "🔴"
        satirlar.append(f"📊 <b>İstatistik</b>  ·  {toplam} işlem  ·  kazanma %{wr:.1f}")
        satirlar.append(f"{net_emoji} Net PnL: <b>{net:+.2f}$</b>  ·  Ortalama: {net/toplam:+.3f}$")
        satirlar.append("")
        satirlar.append("📋 <b>Son 5 işlem</b>")
        for t in list(reversed(gecmis))[:5]:
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            sebep = t.get("not", "")
            satirlar.append(f"  {emoji} {t['symbol'].split('/')[0]:<8} {t['pnl']:+.2f}$  <i>({sebep})</i>")
    else:
        satirlar.append("⚪ Henüz kapanan işlem yok.")

    if acik_detay:
        satirlar.append("")
        satirlar.append("📈 <b>Açık pozisyonlar</b>")
        for sym, anlik in acik_detay:
            e = "🟢" if anlik >= 0 else "🔴"
            satirlar.append(f"  {e} {sym.split('/')[0]:<8} {anlik:+.2f}$")
    return "\n".join(satirlar)


def panel_ayarlar_metni():
    temkinli = btc_temkinli_mod_mu() if TEMKINLI_MOD_AKTIF else False
    with izleme_lock:
        izleme_boyut = len(izleme_listesi)
        izleme_coinler = sorted(s.split("/")[0] for s in izleme_listesi.keys())
    izleme_satiri = f"  Şu an listede: {', '.join(izleme_coinler)}" if izleme_coinler else "  Şu an liste boş"

    if SHORT_AKTIF:
        yon_basligi = "LONG+SHORT"
        yon_aciklama = ("  1) 1D, 4H, 1H üçü de AYNI yönde olmalı (hepsi YUKARI -> LONG, "
                         "hepsi AŞAĞI -> SHORT)\n")
    else:
        yon_basligi = "LONG-only"
        yon_aciklama = "  1) 1D, 4H, 1H üçü de YUKARI olmalı (SADECE LONG)\n"

    return (f"⚙️ LIVE BOT v7.2 (MANUEL ONAY PANELİ + WEB PANELİ + OTOMATİK BİLDİRİM + ANİ HAREKET, otomatik giriş {'AÇIK' if OTOMATIK_GIRIS_AKTIF else 'KAPALI'}) AYARLARI\n\n"
            f"🎯 ŞU ANKİ AKTİF MOD: {aktif_strateji_modu().upper()} "
            f"(STRATEJI_MODU ayarı: {STRATEJI_MODU})\n\n"
            f"Sürüm: v4.2 (22.09.2026 — erken güvenlik çıkışı eklendi: YUKSELEN "
            f"modunda ilk {ERKEN_GUVENLIK_SURE_DK:.0f} dk içinde %{ERKEN_GUVENLIK_MAX_ZARAR_PCT:.1f} "
            f"aleyhe giderse erken çıkılır (IOTX/FLOCK tarzı büyük tekil kayıpları önlemek için). "
            f"Önceki: v4.1 zirveden mesafe filtresi → v4.0 otomatik strateji modu → "
            f"v3.9 akıllı temkinli mod → v3.7 kısmi kâr alma + breakeven → "
            f"14.09.2026 hacim teyidi + pump filtresi → 01.09.2026 fırsatçı "
            f"geçiş → 08.09.2026 bileşik büyüme/8sa/akıllı cooldown/trend gücü → "
            f"10.09.2026 SHORT eklendi → 11.09.2026 SHORT kapatıldı. Şu an: {yon_basligi})\n\n"
            "💰 BU BOT GERÇEK PARA KULLANIYOR.\n\n"
            f"Giriş ({yon_basligi}): Üçlü zaman dilimi trend uyumu + trend gücü + "
            f"dip/tepe yakınlığı + hacim teyidi + pump filtresi\n"
            f"{yon_aciklama}"
            f"  2) 4H trend en az %{MIN_4H_TREND_GUCU_PCT:.1f} güçte olmalı (MA20'den uzaklık)\n"
            "  3) 15m'de swing dip/tepe + dönüş onayı gerekli\n"
            f"  4) Giriş fiyatı swing noktadan en fazla %{GIRIS_MAX_DIP_MESAFE*100:.0f} uzak olmalı\n"
            f"  5) [v3.6] Son 15m mum hacmi, {HACIM_TEYIT_PERIYOT} mum ortalamasının en az "
            f"{HACIM_TEYIT_KATSAYI:.1f} katı olmalı ({'AKTİF' if HACIM_TEYIT_AKTIF else 'KAPALI'})\n"
            f"  6) [v3.6] Coin son 24s'te %{PUMP_FILTRE_ESIK_PCT:.0f}'ten fazla pompalanmamış olmalı "
            f"(LONG için, {'AKTİF' if PUMP_FILTRE_AKTIF else 'KAPALI'})\n"
            f"  7) [v4.1, sadece YUKSELEN modunda] Giriş fiyatı, son {ZIRVE_LOOKBACK} mumun "
            f"zirvesinden en az %{ZIRVEDEN_MIN_MESAFE_PCT*100:.1f} aşağıda olmalı (tam tepede alım önlenir)\n"
            f"  [v4.9] Yüzdelik dilim sıralaması: sadece son 24s getirisi üst %{(1-YUKSELEN_UST_YUZDELIK)*100:.0f}'luk "
            f"dilimde olan coinler aday havuzuna giriyor (basit 'pozitif mi' değil, 'ne kadar güçlü' sıralaması - "
            f"geri veriyle doğrulandı)\n"
            f"  [v4.7] ANLIK volatilite filtresi: son {ANLIK_VOLATILITE_MUM} mumda (≈{ANLIK_VOLATILITE_MUM*15} dk) "
            f"en az %{ANLIK_VOLATILITE_MIN_PCT:.1f} hareket olmalı - 24s'lik gecikmeli ölçüm yerine, "
            f"işlem alınacağı O ANDA hareketli olan coin seçiliyor\n"
            f"  [v5.2] Mum gövde gücü: giriş mumunun gövdesi, toplam aralığın en az %{YUKSELEN_MIN_GOVDE_ORANI*100:.0f}'i "
            f"olmalı - zayıf/kararsız mumlar (giriş sonrası hemen ters gitme riski) elenir. Backtest'te kazanma "
            f"oranı %59.6'dan ~%61'e çıktı\n\n"
            "⚡ ÇIKIŞ:\n"
            f"  [v3.7→v4.4] Kısmi kâr alma (SADECE TREND modunda): pozisyon %{KISMI_KAR_ESIK_PCT*100:.1f}'e ulaşınca "
            f"miktarın %{KISMI_KAR_ORANI*100:.0f}'i kapatılır, kalan SL'i breakeven'e çekilir "
            f"({'AKTİF' if KISMI_KAR_AKTIF else 'KAPALI'}) - YUKSELEN modunda KAPALI (backtest'te net zararlı çıktı)\n"
            f"  TAM HEDEF (TREND modunda): SABİT %{HIZLI_HEDEF_PCT*100:.1f}\n"
            f"  [v4.9] TAM HEDEF (YUKSELEN modunda): SABİT %{YUKSELEN_HEDEF_PCT*100:.1f} - "
            f"backtest'te doğrulanan 'en hızlı ama hâlâ kârlı' seviye "
            f"({'AKTİF - tavan var' if YUKSELEN_TP_TAVAN_AKTIF else 'KAPALI - v5.1: tavan kaldırıldı, iz sürme tek koruma'})\n"
            f"  SL (TREND modunda): swing bazlı, taban %{MIN_SL_PCT*100:.0f} (kısmi alım sonrası breakeven'e çekilir)\n"
            f"  [v4.9] SL (YUKSELEN modunda): SABİT %{YUKSELEN_SL_PCT*100:.1f} - TP ile aynı oran, "
            f"risk/ödül oranı bakiye büyüklüğünden BAĞIMSIZ sabit kalır\n"
            f"  [v5.0, sadece YUKSELEN modunda] İZ SÜRME: kâr %{YUKSELEN_TRAILING_AKTIVASYON_PCT*100:.1f}'e "
            f"ulaşınca SL, zirveden %{YUKSELEN_TRAILING_PAYI_PCT*100:.1f} gerisinden takip etmeye başlar "
            f"({'AKTİF' if YUKSELEN_TRAILING_AKTIF else 'KAPALI'}) - pozisyonun TAMAMI korunur (kısmi kâr alma "
            f"DEĞİL), fiyat devam ederse tam hedefe ulaşılabilir, dönerse kilitlenen kârla çıkılır. Güncel "
            f"veride backtest: net +121$ → +440$ (canlı botun tam giriş mantığıyla doğrulandı, TP tavanı "
            f"kaldırılmış hâliyle)\n"
            f"  [v4.2, sadece YUKSELEN modunda] Erken güvenlik çıkışı: ilk {ERKEN_GUVENLIK_SURE_DK:.0f} dk "
            f"boyunca sürekli kontrol - %{ERKEN_GUVENLIK_MAX_ZARAR_PCT:.1f} aleyhe giderse HEMEN çıkılır "
            f"({'AKTİF' if ERKEN_GUVENLIK_CIKISI_AKTIF else 'KAPALI'})\n"
            f"  Max tutma: {MAX_HOLD_SAAT:.0f} saat\n\n"
            f"💰 MARJİN (bileşik büyüme): bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i "
            f"(taban ${MARJIN_TABAN_USDT:.2f}, tavan ${MARJIN_TAVAN_USDT:.2f})\n"
            f"  [v3.7] Küçük bakiyede efektif taban = min(${MARJIN_TABAN_USDT:.2f}, bakiye/{MAX_POS}) "
            f"- çeşitlendirmeyi korumak için (bakiye ${MARJIN_TABAN_USDT*MAX_POS:.0f}'ı geçince normal tabana döner)\n"
            f"  Şu anki bakiyeyle hesaplanan marjin: ${hesapla_marjin(gercek_bakiye_al() or 0):.2f}\n"
            f"Kaldıraç: {LEV}x\n"
            f"MAX_POS (normal): {MAX_POS} | MAX_POS (şu an geçerli): {efektif_max_pos()}\n\n"
            f"🛑 GÜNLÜK ZARAR FRENİ: {'AKTİF' if GUNLUK_ZARAR_FRENI_AKTIF else 'KAPALI'} "
            f"(bugün gün başı bakiyenin %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}'i kadar zarar olursa yeni işlem durur) | /surtunme: kayma özeti\n"
            f"📈 HİSSE/ETF/EMTİA (RWA) vadelileri: {'DAHİL' if RWA_HISSE_DAHIL else 'DIŞLANDI (kripto çiftleri)'}\n"
            f"🚫 KOVALAMA KORUMASI: {'AKTİF' if KOVALAMA_KORUMA_AKTIF else 'KAPALI'} (fiyat sinyal kapanışının %{KOVALAMA_MAX_PCT:.1f}'ten "
            f"fazla üstündeyse girilmez) | AYNI MUMDAN en fazla {AYNI_MUM_MAX_GIRIS} giriş\n\n"
            f"🔄 TREND DÖNÜŞ AJANI: {'AKTİF' if TREND_AJANI_AKTIF else 'KAPALI (kullanıcı kararı)'}\n\n"
            f"🌡️ TEMKİNLİ MOD: {'AKTİF' if TEMKINLI_MOD_AKTIF else 'KAPALI'} "
            f"(BTC düşerse: {'yeni pozisyon TAMAMEN durur' if TEMKINLI_MOD_TAM_DURDURMA else 'MAX_POS yarıya iner, trend gücü eşiği yükselir (%' + str(MIN_4H_TREND_GUCU_PCT_TEMKINLI) + ')'})\n"
            f"  Şu anki durum: {'⚠️ DEVREDE (BTC 1D+4H düşüşte: MAX_POS yarıya indi, trend gücü eşiği yükseldi - sadece BTC-bağımsız güçlü coinler geçer)' if temkinli else '✅ pasif (BTC 1D+4H yükselişte/karışık, normal çalışıyor)'}\n\n"
            f"👁️ İZLEME LİSTESİ AJANI: max {IZLEME_LISTESI_BOYUTU} coin, "
            f"{IZLEME_TARAMA_ARALIGI_SN//60}dk'da bir genişletiliyor\n"
            f"{izleme_satiri} ({izleme_boyut}/{IZLEME_LISTESI_BOYUTU})\n\n"
            "⚠️ v3.6/v3.7 filtreleri (hacim teyidi, pump filtresi, kısmi kâr alma) "
            "henüz canlıda tam test edilmedi - geçmiş veri analizine dayanan ilk "
            "tahmin değerleridir. Birkaç günlük yeni veri sonrası panel_analiz ile "
            "gözden geçirilmesi gerekir.\n"
            "⚠️ SHORT_AKTIF=true ortam değişkeniyle SHORT tekrar açılabilir, "
            "ama kullanıcı kararıyla şu an kapalı.")


def panel_gecmis_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "📜 Henüz kapanan işlem yok."
    satirlar = ["📜 SON 15 İŞLEM\n"]
    for t in list(reversed(gecmis))[:15]:
        emoji = "🟢" if t["pnl"] >= 0 else "🔴"
        yon_etiket = "LONG" if t.get("yon", "long") == "long" else "SHORT"
        satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} {yon_etiket} {t['pnl']:+.2f}$ "
                         f"[{t.get('not','?')}]\n   {t['zaman']} | 1D:{t.get('1d','?')}/4H:{t.get('4h','?')}/1H:{t.get('1h','?')}")
    return "\n".join(satirlar)


def panel_analiz_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "🔬 ANALİZ\n\nHenüz kapanan işlem yok."
    satirlar = ["🔬 ANALİZ\n", "🚪 Kapanış sebebine göre:"]
    for sebep in sorted(set(t.get("not", "?") for t in gecmis)):
        alt = [t for t in gecmis if t.get("not") == sebep]
        net = sum(t["pnl"] for t in alt)
        w = len([t for t in alt if t["pnl"] > 0])
        satirlar.append(f"  {sebep}: {len(alt)} işlem, %{w/len(alt)*100:.0f} kazanma, net {net:+.2f}$")

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
            entry = d["entry"]
            long_mu = d.get("yon", "long") == "long"
            yon_etiket = "LONG" if long_mu else "SHORT"
            pnl_pct = (guncel - entry) / entry * 100 if long_mu else (entry - guncel) / entry * 100
            anlik_kar = pnl_pct / 100 * d.get("notional", NOTIONAL)
            sure_dk = (time.time() - d["acilis_zamani"]) / 60
            kalan_dk = MAX_HOLD_SAAT * 60 - sure_dk
            satirlar.append(f"{sym} {yon_etiket} (1D:{d.get('1d')}/4H:{d.get('4h')}/1H:{d.get('1h')})\n"
                             f"  Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                             f"  Anlık PnL: {anlik_kar:+.2f}$ | SL:{d['sl']:.6f} | TP:{d.get('tp',0):.6f}\n"
                             f"  Açık süre: {sure_dk:.0f} dk | Max tutmaya kalan: {max(0,kalan_dk):.0f} dk")
        except Exception:
            satirlar.append(f"{sym} (fiyat alınamadı)")
    return "\n".join(satirlar)


def ana_menu_klavye():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("🔍 Tara", callback_data="panel_tara"),
        telebot.types.InlineKeyboardButton("📋 Pozisyonlar", callback_data="panel_pozisyonlar"),
    )
    durdur_baslat_etiket = "🛑 Otomatik Girişi Durdur" if OTOMATIK_GIRIS_AKTIF else "▶️ Otomatik Girişi Başlat"
    markup.row(telebot.types.InlineKeyboardButton(durdur_baslat_etiket, callback_data="panel_durdur_toggle"))
    markup.row(
        telebot.types.InlineKeyboardButton("📊 Özet", callback_data="panel_ozet"),
        telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="panel_ayarlar"),
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📜 Geçmiş", callback_data="panel_gecmis"),
        telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="panel_analiz"),
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📏 Sürtünme", callback_data="panel_surtunme"),
        telebot.types.InlineKeyboardButton("📉 Pozisyon Detayı", callback_data="panel_risk"),
    )
    markup.row(telebot.types.InlineKeyboardButton("🚨 Tümünü Kapat", callback_data="panel_kapat_hepsi_sor"))
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
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye(), parse_mode="HTML")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        veri = call.data
        try:
            if veri == "panel_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye(), parse_mode="HTML")
            elif veri == "panel_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu(), parse_mode="HTML")
            elif veri == "panel_tara":
                bot.answer_callback_query(call.id, "Taranıyor...")
                _sahte_msg = type("M", (), {"chat": type("C", (), {"id": call.message.chat.id})()})()
                tara_komutu(_sahte_msg)
                return
            elif veri == "panel_pozisyonlar":
                _sahte_msg = type("M", (), {"chat": type("C", (), {"id": call.message.chat.id})()})()
                pozisyonlar_komutu(_sahte_msg)
                bot.answer_callback_query(call.id)
                return
            elif veri == "panel_durdur_toggle":
                global OTOMATIK_GIRIS_AKTIF
                OTOMATIK_GIRIS_AKTIF = not OTOMATIK_GIRIS_AKTIF
                bot.answer_callback_query(call.id, f"Otomatik giriş {'açıldı' if OTOMATIK_GIRIS_AKTIF else 'durduruldu'}.")
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye(), parse_mode="HTML")
                return
            elif veri == "panel_surtunme":
                bot.edit_message_text(surtunme_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_kapat_hepsi_sor":
                with state_lock:
                    n_poz = len(trade_state)
                with manuel_kilit:
                    n_bek = len(manuel_limit_emirler)
                onay_markup = telebot.types.InlineKeyboardMarkup()
                onay_markup.row(
                    telebot.types.InlineKeyboardButton("✅ Evet, HEPSİNİ kapat", callback_data="panel_kapat_hepsi_evet"),
                    telebot.types.InlineKeyboardButton("❌ Vazgeç", callback_data="panel_ana"),
                )
                bot.edit_message_text(
                    f"⚠️ <b>{n_poz} açık pozisyon</b> piyasa fiyatından kapatılacak, "
                    f"<b>{n_bek} bekleyen limit emir</b> iptal edilecek. Emin misin?",
                    call.message.chat.id, call.message.message_id, reply_markup=onay_markup, parse_mode="HTML")
                bot.answer_callback_query(call.id)
                return
            elif veri == "panel_kapat_hepsi_evet":
                kapatilan, iptal_edilen = tum_pozisyonlari_kapat()
                bot.edit_message_text(
                    f"🚨 Kapatıldı: {', '.join(s.split('/')[0] for s in kapatilan) or 'yok'}\n"
                    f"🗑️ İptal edildi: {', '.join(s.split('/')[0] for s in iptal_edilen) or 'yok'}",
                    call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
                bot.answer_callback_query(call.id)
                return
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

    @bot.message_handler(commands=["surtunme"])
    def surtunme_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, surtunme_ozet_metni())

    # ════════════════════════════════════════════
    # v6.0: MANUEL ONAY PANELİ - /tara, /ac, /pozisyonlar, /durdur, /baslat
    # ════════════════════════════════════════════
    def _rsi_emoji(r):
        if r is None: return "⚪"
        if r >= 70: return "🟥"
        if r <= 30: return "🟦"
        return "🟩"

    def _yon_emoji(y):
        return {"YUKARI": "📈", "AŞAĞI": "📉"}.get(y, "➖")

    def manuel_kart_metni(aday, btc_baglam):
        long_mu = aday["yon"] == "long"
        renk = "🟢" if long_mu else "🔴"
        ok = "UZUN" if long_mu else "KISA"
        risk = abs(aday["fiyat"] - aday["sl"]); odul = abs(aday["tp"] - aday["fiyat"])
        rr = aday["rr"]
        rr_emoji = "💎" if rr >= 2 else ("✅" if rr >= 1.5 else "🟡")
        sym_ad = aday["symbol"].split("/")[0]
        return (
            f"{renk} <b>{sym_ad}</b>  ·  <b>{ok}</b> aday\n"
            f"<i>BTC {_yon_emoji(btc_baglam['y4'])} 4S {btc_baglam['y4']} (RSI {btc_baglam['r4']})"
            f"  ·  {_yon_emoji(btc_baglam['y1'])} 1S {btc_baglam['y1']} (RSI {btc_baglam['r1']})</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💲 Fiyat: <b>{aday['fiyat']:.8g}</b>\n"
            f"{_yon_emoji(aday['y4'])} 4S  <b>{aday['y4']}</b>   {_rsi_emoji(aday['r4'])} RSI {aday['r4']}\n"
            f"{_yon_emoji(aday['y1'])} 1S  <b>{aday['y1']}</b>   {_rsi_emoji(aday['r1'])} RSI {aday['r1']}\n"
            f"📏 MA20'den: <b>%{aday['ma_mesafe']:+.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Plan</b> <i>(1S/4S swing destek-direnç — kesin sinyal değil)</i>\n"
            f"   Giriş (limit): <b>{aday['fiyat']:.8g}</b>\n"
            f"   🛑 SL: <b>{aday['sl']:.8g}</b>  (-%{risk/aday['fiyat']*100:.1f})\n"
            f"   🏁 TP: <b>{aday['tp']:.8g}</b>  (+%{odul/aday['fiyat']*100:.1f})\n"
            f"   {rr_emoji} R/R: <b>{rr}</b>\n"
            f"{likidasyon_uyari_satiri(risk / aday['fiyat'], aday.get('lev'), aday.get('mod'))}"
            f"{ayar_satiri(aday)}"
            f"   ⚡ İz sürme: kâr %{YUKSELEN_TRAILING_AKTIVASYON_PCT*100:.1f}'te aktif, %{YUKSELEN_TRAILING_PAYI_PCT*100:.1f} pay"
        )

    def kart_markup(token, aday=None):
        """Kartın düğmeleri: ana satır (Aç/Düzenle/Geç) + kaldıraç + marjin + marjin modu seçimleri (seçili olan ✅)."""
        B = telebot.types.InlineKeyboardButton
        m = telebot.types.InlineKeyboardMarkup()
        ani = bool(aday and aday.get("kart_tip") == "ani")
        e1, e2, e3 = ("✅ Gir", "✏️ Düzenle", "❌ Pas") if ani else ("✅ Aç", "✏️ Düzenle", "❌ Geç")
        m.row(B(e1, callback_data=f"macik:{token}:ac"), B(e2, callback_data=f"macik:{token}:duzenle"),
              B(e3, callback_data=f"macik:{token}:gec"))
        if aday is not None:
            lev_s = int(aday.get("lev") or LEV)
            m.row(*[B(("✅ " if lev_s == v else "") + f"{v}x", callback_data=f"mayar:{token}:lev:{v}") for v in LEV_SECENEKLERI])
            mj = float(aday.get("marjin", MANUEL_MARJIN_VARSAYILAN_USDT))
            m.row(*[B(("✅ " if abs(mj - v) < 1e-9 else "") + f"${v:g}", callback_data=f"mayar:{token}:marjin:{v:g}")
                    for v in MARJIN_SECENEKLERI])
            mod = aday.get("mod") or MARJIN_MODU
            m.row(B(("✅ " if mod == "isolated" else "") + "🔒 İzole", callback_data=f"mayar:{token}:mod:isolated"),
                  B(("✅ " if mod == "cross" else "") + "🌐 Cross", callback_data=f"mayar:{token}:mod:cross"))
        return m

    def manuel_kart_markup(token, aday=None):
        return kart_markup(token, aday)

    def kart_hazirla(aday, tip, btc_baglam, onek=""):
        """Karta varsayılan ayarları (kaldıraç, marjin, marjin modu) ve yeniden çizim için gerekenleri ekler."""
        aday.setdefault("lev", LEV)
        aday.setdefault("marjin", MANUEL_MARJIN_VARSAYILAN_USDT)
        aday.setdefault("mod", MARJIN_MODU)
        aday["kart_tip"] = tip
        aday["_btc"] = btc_baglam
        aday["_onek"] = onek
        return aday

    def kart_metni(aday):
        govde = (ani_hareket_kart_metni(aday, aday["_btc"]) if aday.get("kart_tip") == "ani"
                 else manuel_kart_metni(aday, aday["_btc"]))
        return aday.get("_onek", "") + govde

    def otomatik_bildirim_gonder(aday, btc_baglam):
        token = uuid.uuid4().hex[:10]
        with manuel_kilit:
            manuel_bekleyen[token] = aday
        kart_hazirla(aday, "manuel", btc_baglam, "🔔 <b>OTOMATİK BİLDİRİM</b> (arka plan taraması, karar hâlâ sende)\n\n")
        try:
            bot.send_message(CHAT_ID, kart_metni(aday), reply_markup=kart_markup(token, aday), parse_mode="HTML")
        except Exception as e:
            log.warning(f"[OTOMATIK_BILDIRIM] gönderilemedi: {e}")

    def otomatik_bildirim_loop():
        while True:
            try:
                time.sleep(OTOMATIK_BILDIRIM_ARALIK_SN)
                if not OTOMATIK_BILDIRIM_AKTIF:
                    continue
                bulunanlar, btc_baglam = manuel_tarama_yap()
                simdi = time.time()
                for aday in bulunanlar:
                    anahtar = f"{aday['symbol']}:{aday['yon']}"
                    son = otomatik_bildirim_gecmis.get(anahtar, 0)
                    if simdi - son < OTOMATIK_BILDIRIM_COOLDOWN_SN:
                        continue    # bu kurulum için yakın zamanda zaten haber verildi
                    otomatik_bildirim_gecmis[anahtar] = simdi
                    otomatik_bildirim_gonder(aday, btc_baglam)
            except Exception as e:
                log.error(f"[OTOMATIK_BILDIRIM_LOOP] {e}")
                time.sleep(30)

    @bot.message_handler(commands=["bildirimac"])
    def bildirimac_komutu(msg):
        if not yetkili_mi(msg):
            return
        global OTOMATIK_BILDIRIM_AKTIF
        OTOMATIK_BILDIRIM_AKTIF = True
        bot.send_message(msg.chat.id, f"🔔 Otomatik bildirim açık. Her {OTOMATIK_BILDIRIM_ARALIK_SN//60} dakikada bir arka planda taranır, temiz kurulum bulunursa haber verilir (işlem açılmaz).")

    @bot.message_handler(commands=["bildirimkapat"])
    def bildirimkapat_komutu(msg):
        if not yetkili_mi(msg):
            return
        global OTOMATIK_BILDIRIM_AKTIF
        OTOMATIK_BILDIRIM_AKTIF = False
        bot.send_message(msg.chat.id, "🔕 Otomatik bildirim kapatıldı. /tara ile elle taramaya devam edebilirsin.")

    def ani_hareket_kart_metni(aday, btc_baglam):
        long_mu = aday["yon"] == "long"
        renk = "🟢" if long_mu else "🔴"
        baslik = "📈 Bu coin YÜKSELEBİLİR" if long_mu else "📉 Bu coin DÜŞEBİLİR"
        yon_sismis = "çökmüş (son 3 günde" if long_mu else "şişmiş (son 3 günde"
        sym_ad = aday["symbol"].split("/")[0]
        sl, tp, rr = aday["sl"], aday["tp"], aday["rr"]
        risk = abs(aday["fiyat"] - sl); odul = abs(tp - aday["fiyat"])
        rr_emoji = "💎" if rr >= 2 else ("✅" if rr >= 1.5 else "🟡")
        return (
            f"{renk} <b>{baslik}</b>\n"
            f"<b>{sym_ad}</b> — {yon_sismis} %{aday['hareket_3g']:+.1f})\n"
            f"<i>BTC {btc_baglam['y4']} (RSI {btc_baglam['r4']}) / {btc_baglam['y1']} (RSI {btc_baglam['r1']})</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Son {ANI_HAREKET_PENCERE_DK} dakikada %{aday['hareket_pencere']:+.2f} hareket, "
            f"hacim x{aday['hacim_carpani']:.1f}\n"
            f"💲 Fiyat: <b>{aday['fiyat']:.8g}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Plan</b> <i>(swing destek-direnç — kesin sinyal değil)</i>\n"
            f"   Giriş (limit): <b>{aday['fiyat']:.8g}</b>\n"
            f"   🛑 SL: <b>{sl:.8g}</b>  (-%{risk/aday['fiyat']*100:.1f})\n"
            f"   🏁 TP: <b>{tp:.8g}</b>  (+%{odul/aday['fiyat']*100:.1f})\n"
            f"   {rr_emoji} R/R: <b>{rr}</b>\n"
            f"{likidasyon_uyari_satiri(risk / aday['fiyat'], aday.get('lev'), aday.get('mod'))}"
            f"{ayar_satiri(aday)}"
            f"{gecmis_istatistik_satiri(aday['yon'], aday.get('lev'))}"
        )

    def ani_hareket_gonder(aday, btc_baglam):
        token = uuid.uuid4().hex[:10]
        with manuel_kilit:
            manuel_bekleyen[token] = aday
        kart_hazirla(aday, "ani", btc_baglam)
        try:
            bot.send_message(CHAT_ID, kart_metni(aday), reply_markup=kart_markup(token, aday), parse_mode="HTML")
        except Exception as e:
            log.warning(f"[ANI_HAREKET_GONDER] gönderilemedi: {e}")

    def ani_hareket_loop():
        while True:
            try:
                time.sleep(ANI_HAREKET_ARALIK_SN)
                if not ANI_HAREKET_AKTIF:
                    continue
                bulunanlar = ani_hareket_tara()
                if not bulunanlar:
                    continue
                d4b, d1b = get_df("BTC/USDT:USDT", "4h", 150), get_df("BTC/USDT:USDT", "1h", 150)
                btc_baglam = {
                    "y4": trend_yon(d4b) if d4b is not None else "?",
                    "y1": trend_yon(d1b) if d1b is not None else "?",
                    "r4": round(rsi_hesapla(d4b["close"], MANUEL_RSI_PERIYOT), 1) if d4b is not None else None,
                    "r1": round(rsi_hesapla(d1b["close"], MANUEL_RSI_PERIYOT), 1) if d1b is not None else None,
                }
                simdi = time.time()
                for aday in bulunanlar:
                    anahtar = f"{aday['symbol']}:{aday['yon']}"
                    son = ani_hareket_gecmis.get(anahtar, 0)
                    if simdi - son < ANI_HAREKET_COOLDOWN_SN:
                        continue
                    long_mu = aday["yon"] == "long"
                    d1_sym = get_df(aday["symbol"], "1h", 150)
                    d4_sym = get_df(aday["symbol"], "4h", 150)
                    if d1_sym is None or d4_sym is None:
                        continue
                    sonuc = manuel_swing_sl_tp(d1_sym, d4_sym, aday["fiyat"], long_mu,
                                              ANI_HAREKET_SL_TAVAN_PCT / 100.0 if ANI_HAREKET_SL_TAVAN_PCT > 0 else None)
                    if sonuc is None:
                        continue
                    aday["sl"], aday["tp"], aday["rr"] = sonuc
                    ani_hareket_gecmis[anahtar] = simdi
                    ani_hareket_gonder(aday, btc_baglam)
            except Exception as e:
                log.error(f"[ANI_HAREKET_LOOP] {e}")
                time.sleep(30)

    @bot.message_handler(commands=["anihareketac"])
    def anihareketac_komutu(msg):
        if not yetkili_mi(msg):
            return
        global ANI_HAREKET_AKTIF
        ANI_HAREKET_AKTIF = True
        bot.send_message(msg.chat.id, f"🔔 Ani hareket alarmı açık.\nKISA: 3 günde %{ANI_HAREKET_3GUN_ESIK_PCT:.0f}+ şişmiş coin, son {ANI_HAREKET_PENCERE_DK} dk'da %{ANI_HAREKET_ESIK_KISA_PCT:.0f}+ düşüş, hacim teyitli.\nUZUN: 3 günde %{ANI_HAREKET_UZUN_MIN_3GUN_PCT:.0f}+ çökmüş coin, son {ANI_HAREKET_PENCERE_DK} dk'da %{ANI_HAREKET_ESIK_PCT:.0f}+ yükseliş, hacim teyitli.")

    @bot.message_handler(commands=["anihareketkapat"])
    def anihareketkapat_komutu(msg):
        if not yetkili_mi(msg):
            return
        global ANI_HAREKET_AKTIF
        ANI_HAREKET_AKTIF = False
        bot.send_message(msg.chat.id, "🔕 Ani hareket alarmı kapatıldı.")

    @bot.message_handler(commands=["tara"])
    def tara_komutu(msg):
        if not yetkili_mi(msg):
            return
        durum_mesaji = bot.send_message(msg.chat.id, "🔍 Taranıyor (4S+1S, ilk 20 yükselen + ilk 20 düşen)...")
        def isle():
            try:
                bulunanlar, btc_baglam = manuel_tarama_yap()
            except Exception as e:
                bot.edit_message_text(f"⚠️ Tarama başarısız: {e}", msg.chat.id, durum_mesaji.message_id)
                return
            if not bulunanlar:
                bot.edit_message_text(
                    f"🔎 <b>BTC</b>: {_yon_emoji(btc_baglam['y4'])} 4S {btc_baglam['y4']} (RSI {btc_baglam['r4']})"
                    f"  ·  {_yon_emoji(btc_baglam['y1'])} 1S {btc_baglam['y1']} (RSI {btc_baglam['r1']})\n\n"
                    f"⚪ Şu an temiz bir 4S+1S kurulumu yok. Zorlamıyorum, birazdan tekrar dene.",
                    msg.chat.id, durum_mesaji.message_id, parse_mode="HTML")
                return
            bot.edit_message_text(f"✅ <b>{len(bulunanlar)} aday</b> bulundu:", msg.chat.id, durum_mesaji.message_id, parse_mode="HTML")
            for aday in bulunanlar:
                token = uuid.uuid4().hex[:10]
                with manuel_kilit:
                    manuel_bekleyen[token] = aday
                kart_hazirla(aday, "manuel", btc_baglam)
                bot.send_message(msg.chat.id, kart_metni(aday), reply_markup=kart_markup(token, aday), parse_mode="HTML")
        threading.Thread(target=isle, daemon=True).start()

    @bot.callback_query_handler(func=lambda call: call.data.startswith("macik:"))
    def manuel_kart_callback(call):
        if not yetkili_mi(call):
            return
        _, token, aksiyon = call.data.split(":", 2)
        with manuel_kilit:
            aday = manuel_bekleyen.get(token)
        if not aday:
            bot.answer_callback_query(call.id, "Bu kart artık geçerli değil (süresi doldu ya da işlendi).")
            return
        if aksiyon == "gec":
            with manuel_kilit:
                manuel_bekleyen.pop(token, None)
            bot.edit_message_text(f"❌ Geçildi: {aday['symbol'].split('/')[0]}", call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return
        if aksiyon == "duzenle":
            manuel_metin_bekleyen[call.message.chat.id] = token
            bot.send_message(call.message.chat.id,
                              f"{aday['symbol'].split('/')[0]} için yeni SL ve TP'yi tek satırda yaz (örnek: `0.0500 0.0555`).",
                              parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            return
        if aksiyon == "ac":
            # Fiyatı tazeden kontrol et (kart eski olabilir)
            try:
                simdi = safe(exchange.fetch_ticker(aday["symbol"]).get("last"))
            except Exception as e:
                bot.answer_callback_query(call.id, f"Fiyat alınamadı: {e}", show_alert=True)
                return
            long_mu = aday["yon"] == "long"
            kayma = ((simdi - aday["fiyat"]) / aday["fiyat"] * 100) if long_mu else ((aday["fiyat"] - simdi) / aday["fiyat"] * 100)
            if abs(kayma) > 1.0:
                bot.answer_callback_query(call.id, f"Fiyat %{kayma:+.2f} kaymış ({simdi:.8g}). Yine de limit {aday['fiyat']:.8g}'ten emir konur, dolmayabilir.", show_alert=True)
            basarili, mesaj = manuel_limit_ac(aday, aday["sl"], aday["tp"], aday.get("marjin"))
            with manuel_kilit:
                manuel_bekleyen.pop(token, None)
            bot.edit_message_text(f"{'✅' if basarili else '⚠️'} {mesaj}", call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("mayar:"))
    def ayar_callback(call):
        """Kart üstündeki kaldıraç / marjin / marjin modu düğmeleri: seçimi karta yazar ve kartı yeniden çizer."""
        if not yetkili_mi(call):
            return
        try:
            _, token, anahtar, deger = call.data.split(":", 3)
        except ValueError:
            bot.answer_callback_query(call.id)
            return
        with manuel_kilit:
            aday = manuel_bekleyen.get(token)
        if not aday:
            bot.answer_callback_query(call.id, "Bu kart artık geçerli değil (süresi doldu ya da işlendi).")
            return
        try:
            if anahtar == "lev" and int(deger) in LEV_SECENEKLERI:
                aday["lev"] = int(deger); secim = f"Kaldıraç {int(deger)}x"
            elif anahtar == "marjin" and float(deger) in MARJIN_SECENEKLERI:
                aday["marjin"] = float(deger); secim = f"Marjin ${float(deger):g}"
            elif anahtar == "mod" and deger in ("isolated", "cross"):
                aday["mod"] = deger; secim = f"Marjin modu: {mod_etiketi(deger)}"
            else:
                raise ValueError("geçersiz seçim")
        except Exception:
            bot.answer_callback_query(call.id, "Geçersiz seçim.")
            return
        try:
            bot.edit_message_text(kart_metni(aday), call.message.chat.id, call.message.message_id,
                                  reply_markup=kart_markup(token, aday), parse_mode="HTML")
        except Exception as e:
            if "message is not modified" not in str(e):
                log.warning(f"[AYAR_CALLBACK] {e}")
        bot.answer_callback_query(call.id, secim)

    @bot.message_handler(commands=["ac"])
    def ac_komutu(msg):
        # /ac SEMBOL long|short GIRIS SL TP [MARJIN]  -- biz elle bulduğumuz bir işlemi doğrudan açmak için
        # MARJIN verilmezse MANUEL_MARJIN_VARSAYILAN_USDT kullanılır.
        if not yetkili_mi(msg):
            return
        try:
            parcalar = msg.text.split()[1:]
            if len(parcalar) not in (5, 6):
                raise ValueError("parametre sayısı 5 ya da 6 olmalı")
            sembol_ham, yon = parcalar[0], parcalar[1].lower()
            giris, sl, tp = float(parcalar[2]), float(parcalar[3]), float(parcalar[4])
            marjin = float(parcalar[5]) if len(parcalar) == 6 else None
            sym = sembol_ham.upper() if "/" in sembol_ham else f"{sembol_ham.upper()}/USDT:USDT"
            if yon not in ("long", "short"):
                raise ValueError("yon long ya da short olmalı")
        except Exception as e:
            bot.send_message(msg.chat.id,
                "Kullanım: /ac SEMBOL long|short GIRIS SL TP [MARJIN]\n"
                "Örnek: /ac PUMP long 0.00522 0.00506 0.00555\n"
                f"Örnek (marjin belirterek): /ac PUMP long 0.00522 0.00506 0.00555 8\n"
                f"(hata: {e})")
            return
        aday = {"symbol": sym, "yon": yon, "fiyat": giris, "y4": "-", "y1": "-"}
        basarili, mesaj = manuel_limit_ac(aday, sl, tp, marjin)
        bot.send_message(msg.chat.id, f"{'✅' if basarili else '⚠️'} {mesaj}")

    @bot.message_handler(commands=["pozisyonlar"])
    def pozisyonlar_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            durum_kopya = dict(trade_state)
        with manuel_kilit:
            bekleyen_kopya = dict(manuel_limit_emirler)
        if not durum_kopya and not bekleyen_kopya:
            bot.send_message(msg.chat.id, "Açık pozisyon ya da bekleyen emir yok.")
            return
        for sym, d in durum_kopya.items():
            try:
                simdi = safe(exchange.fetch_ticker(sym).get("last"))
            except Exception:
                simdi = d["entry"]
            long_mu = d["yon"] == "long"
            pnl_pct = (simdi/d["entry"]-1)*100 if long_mu else (d["entry"]/simdi-1)*100
            m = telebot.types.InlineKeyboardMarkup()
            m.row(telebot.types.InlineKeyboardButton("❌ Kapat", callback_data=f"mapoz:{sym}:kapat"))
            pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
            bot.send_message(msg.chat.id,
                f"{'🟢' if long_mu else '🔴'} <b>{sym.split('/')[0]}</b>  <i>[{d.get('acilis_modu','?')}]</i>\n"
                f"Giriş <b>{d['entry']:.8g}</b> → Şimdi <b>{simdi:.8g}</b>  {pnl_emoji} <b>%{pnl_pct:+.2f}</b>\n"
                f"🛑 SL {d['sl']:.8g}  ·  🏁 TP {d['tp']:.8g}  ·  ⚡ İz sürme: {'AKTİF' if d.get('trailing_aktif') else 'henüz değil'}",
                reply_markup=m, parse_mode="HTML")
        for sym, k in bekleyen_kopya.items():
            m = telebot.types.InlineKeyboardMarkup()
            m.row(telebot.types.InlineKeyboardButton("🗑️ İptal Et", callback_data=f"mapoz:{sym}:iptal"))
            bot.send_message(msg.chat.id, f"📝 {sym.split('/')[0]} bekleyen limit emir @ {k['entry_hedef']:.8g}", reply_markup=m)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("mapoz:"))
    def pozisyon_callback(call):
        if not yetkili_mi(call):
            return
        _, sym, aksiyon = call.data.split(":", 2)
        if aksiyon == "iptal":
            ok = manuel_limit_iptal(sym, "panelden iptal")
            bot.edit_message_text(f"{'🗑️ İptal edildi' if ok else 'Bulunamadı'}: {sym.split('/')[0]}", call.message.chat.id, call.message.message_id)
        elif aksiyon == "kapat":
            with state_lock:
                durum = trade_state.get(sym)
            if not durum:
                bot.answer_callback_query(call.id, "Pozisyon zaten kapalı.")
                return
            try:
                kapanis_yonu = "sell" if durum["yon"] == "long" else "buy"
                exchange.create_market_order(sym, kapanis_yonu, durum["qty"], params={"reduceOnly": True})
                bot.edit_message_text(f"❌ Kapatıldı: {sym.split('/')[0]}", call.message.chat.id, call.message.message_id)
            except Exception as e:
                bot.answer_callback_query(call.id, f"Kapatma başarısız: {e}", show_alert=True)
                return
        bot.answer_callback_query(call.id)

    @bot.message_handler(commands=["durdur"])
    def durdur_komutu(msg):
        if not yetkili_mi(msg):
            return
        global OTOMATIK_GIRIS_AKTIF
        OTOMATIK_GIRIS_AKTIF = False
        bot.send_message(msg.chat.id, "🛑 Otomatik giriş durduruldu. Açık pozisyonlar yönetilmeye devam eder. Manuel /tara ve /ac her zaman çalışır.")

    @bot.message_handler(commands=["baslat"])
    def baslat_komutu(msg):
        if not yetkili_mi(msg):
            return
        global OTOMATIK_GIRIS_AKTIF
        OTOMATIK_GIRIS_AKTIF = True
        bot.send_message(msg.chat.id, "▶️ Otomatik giriş tekrar aktif.")

    @bot.message_handler(func=lambda m: m.chat.id in manuel_metin_bekleyen)
    def duzenle_metin_handler(msg):
        if not yetkili_mi(msg):
            return
        token = manuel_metin_bekleyen.pop(msg.chat.id)
        with manuel_kilit:
            aday = manuel_bekleyen.get(token)
        if not aday:
            bot.send_message(msg.chat.id, "Bu kartın süresi doldu.")
            return
        try:
            parcalar = [float(x) for x in msg.text.replace(",", " ").split()]
            if len(parcalar) not in (2, 3):
                raise ValueError("2 ya da 3 sayı olmalı")
            yeni_sl, yeni_tp = parcalar[0], parcalar[1]
            yeni_marjin = parcalar[2] if len(parcalar) == 3 else aday.get("marjin")
        except Exception:
            bot.send_message(msg.chat.id,
                "Anlaşılamadı. Şu formatlardan biriyle yaz:\n"
                "SL TP  (örnek: 0.0500 0.0555)\n"
                "SL TP MARJIN  (örnek: 0.0500 0.0555 8)")
            manuel_metin_bekleyen[msg.chat.id] = token
            return
        long_mu = aday["yon"] == "long"
        if (long_mu and not (yeni_sl < aday["fiyat"] < yeni_tp)) or (not long_mu and not (yeni_tp < aday["fiyat"] < yeni_sl)):
            beklenen = "SL < Giriş < TP" if long_mu else "TP < Giriş < SL"
            bot.send_message(msg.chat.id, f"Bu yön ({'UZUN' if long_mu else 'KISA'}) için {beklenen} olmalı. Giriş: {aday['fiyat']:.8g}. Tekrar yaz.")
            manuel_metin_bekleyen[msg.chat.id] = token
            return
        if yeni_marjin is not None and yeni_marjin <= 0:
            bot.send_message(msg.chat.id, "Marjin pozitif olmalı. Tekrar yaz.")
            manuel_metin_bekleyen[msg.chat.id] = token
            return
        aday["sl"], aday["tp"] = yeni_sl, yeni_tp
        if yeni_marjin is not None:
            aday["marjin"] = yeni_marjin
        risk = abs(aday["fiyat"]-yeni_sl); odul = abs(yeni_tp-aday["fiyat"])
        aday["rr"] = round(odul/risk, 2) if risk > 0 else 0
        with manuel_kilit:
            manuel_bekleyen[token] = aday
        bot.send_message(msg.chat.id, "✏️ <b>Güncellendi</b>\n\n" + kart_metni(aday), reply_markup=kart_markup(token, aday),
                         parse_mode="HTML")

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
            dosya.name = f"live2_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
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
        tg(f"⚠️ UYARI: borsada açık ama state'te olmayan pozisyonlar: {sorted(sadece_borsada)}\n"
           f"(Eski live_bot'tan kalma bir pozisyon olabilir - manuel kontrol et.)")


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

                yon_kayitli = durum.get("yon", "long")
                long_mu = (yon_kayitli == "long")
                aranan_yon = "yukselis" if long_mu else "dusus"

                # v5.2 GÜVENLİK DÜZELTMESİ: eski koddan (v5.1 öncesi) kalma
                # açık pozisyonlar, hâlâ eski sabit %3 TP'yi taşıyor olabilir
                # (ZRO örneğinde görüldü - iz sürme SL'i doğru yükseltiyordu
                # ama pozisyon eski %3 tavana takılıp erken kapandı). Eğer
                # YUKSELEN modunda TP tavanı artık kapalıysa ve bu pozisyonun
                # TP'si hâlâ makul/ulaşılabilir bir seviyedeyse (yani "ulaşılamaz
                # tavan" olarak ayarlanmamışsa), otomatik olarak düzeltiyoruz.
                if (durum.get("acilis_modu") == "yukselen" and not YUKSELEN_TP_TAVAN_AKTIF
                        and durum.get("tp") is not None):
                    eski_tp_makul_mu = (durum["tp"] < durum["entry"] * 1.5 if long_mu
                                         else durum["tp"] > durum["entry"] * 0.5)
                    if eski_tp_makul_mu:
                        yeni_tp = durum["entry"] * 2.0 if long_mu else durum["entry"] * 0.5
                        with state_lock:
                            if sym in trade_state:
                                trade_state[sym]["tp"] = yeni_tp
                        durumu_diske_yaz()
                        durum = trade_state.get(sym, durum)
                        log.info(f"[TP_DUZELTME] {sym} eski sabit TP kaldırıldı, "
                                 f"ulaşılamaz tavana güncellendi")

                # ── v5.0 YENİ: İZ SÜRME (trailing stop) - sadece YUKSELEN
                # modunda açılan pozisyonlar için. Kısmi kâr almadan farklı:
                # pozisyonun TAMAMI korunuyor, sadece SL kârın gerisinden
                # takip ediyor. Backtest'te (güncel veri) net kârı +121$'dan
                # +519$'a çıkardığı doğrulandı.
                if YUKSELEN_TRAILING_AKTIF and durum.get("acilis_modu") in ("yukselen", "manuel"):
                    en_yuksek = durum.get("en_yuksek_fiyat", durum["entry"])
                    yeni_en_yuksek = max(en_yuksek, guncel) if long_mu else min(en_yuksek, guncel)
                    if yeni_en_yuksek != en_yuksek:
                        with state_lock:
                            if sym in trade_state:
                                trade_state[sym]["en_yuksek_fiyat"] = yeni_en_yuksek
                        durumu_diske_yaz()
                        en_yuksek = yeni_en_yuksek

                    ilerleme_pct = ((en_yuksek - durum["entry"]) / durum["entry"] if long_mu
                                     else (durum["entry"] - en_yuksek) / durum["entry"])
                    if ilerleme_pct >= YUKSELEN_TRAILING_AKTIVASYON_PCT:
                        yeni_sl = (en_yuksek * (1 - YUKSELEN_TRAILING_PAYI_PCT) if long_mu
                                   else en_yuksek * (1 + YUKSELEN_TRAILING_PAYI_PCT))
                        eski_sl = durum["sl"]
                        sl_iyilesti = (yeni_sl > eski_sl) if long_mu else (yeni_sl < eski_sl)
                        if sl_iyilesti:
                            eski_sl_id = durum.get("sl_emir_id")
                            if eski_sl_id:
                                try:
                                    exchange.cancel_order(eski_sl_id, sym)
                                except Exception as e:
                                    log.warning(f"[TRAILING_SL_IPTAL] {sym}: {e}")
                            kapanis_yonu_trail = "sell" if long_mu else "buy"
                            yeni_sl_fiyat = float(exchange.price_to_precision(sym, yeni_sl))
                            yeni_sl_id = None
                            try:
                                sl_emri = exchange.create_order(
                                    sym, "market", kapanis_yonu_trail, durum["qty"], None,
                                    {"reduceOnly": True, "stopLossPrice": yeni_sl_fiyat})
                                yeni_sl_id = sl_emri.get("id")
                            except Exception as e:
                                log.warning(f"[TRAILING_SL_YENI] {sym}: {e}")
                            if yeni_sl_id:
                                ilk_aktivasyon = not durum.get("trailing_aktif", False)
                                with state_lock:
                                    if sym in trade_state:
                                        trade_state[sym]["sl"] = yeni_sl
                                        trade_state[sym]["sl_emir_id"] = yeni_sl_id
                                        trade_state[sym]["trailing_aktif"] = True
                                durumu_diske_yaz()
                                durum = trade_state.get(sym, durum)
                                log.info(f"[TRAILING] {sym} SL güncellendi: {yeni_sl_fiyat:.6f} "
                                         f"(zirve: {en_yuksek:.6f})")
                                # v5.6 TEŞHİS (yalnızca okur): eski stop'lar borsada değişiyor mu birikiyor mu?
                                sayac = durum.get("trailing_guncelleme_sayisi", 0) + 1
                                with state_lock:
                                    if sym in trade_state:
                                        trade_state[sym]["trailing_guncelleme_sayisi"] = sayac
                                if sayac in (1, 4):
                                    stoplar = borsa_stoplarini_oku(sym)
                                    if stoplar is not None:
                                        tetikler = [t for _, t, _ in stoplar]
                                        log.info(f"[STOP_TESHIS] {sym} güncelleme#{sayac}: borsada {len(stoplar)} TP/SL plan emri: {stoplar}")
                                        tg(f"🔎 [STOP TEŞHİS] {sym} (iz sürme güncellemesi #{sayac}): borsada "
                                           f"{len(stoplar)} stop/plan emri var, tetik fiyatları: {tetikler}\n"
                                           f"1 ise borsa eskiyi yeniyle değiştiriyor (iyi). 1'den fazlaysa eski stoplar birikiyor.")
                                if ilk_aktivasyon:
                                    tg(f"🔒 [İZ SÜRME AKTİF] {sym}\n"
                                       f"Kâr %{YUKSELEN_TRAILING_AKTIVASYON_PCT*100:.1f}'e ulaştı, "
                                       f"SL kilitlendi: {yeni_sl_fiyat:.6f}\n"
                                       f"Zirve: {en_yuksek:.6f} | Bundan sonra sadece yükselecek, "
                                       f"düşerse bu kilitle çıkılır")

                # ── v4.2 YENİ: ERKEN GÜVENLİK ÇIKIŞI (sadece YUKSELEN modunda
                # açılan, henüz kısmi kâr alınmamış pozisyonlar) ──
                if (ERKEN_GUVENLIK_CIKISI_AKTIF and durum.get("acilis_modu") == "yukselen"
                        and not durum.get("kismi_alindi", False)):
                    gecen_dk = (time.time() - durum["acilis_zamani"]) / 60
                    ilerleme_pct = ((guncel - durum["entry"]) / durum["entry"] * 100 if long_mu
                                     else (durum["entry"] - guncel) / durum["entry"] * 100)
                    if gecen_dk < ERKEN_GUVENLIK_SURE_DK:
                        if ilerleme_pct <= -ERKEN_GUVENLIK_MAX_ZARAR_PCT:
                            log.info(f"[ERKEN_GUVENLIK] {sym} ilk {gecen_dk:.0f} dk içinde "
                                     f"%{ilerleme_pct:.2f} aleyhe gitti, erken çıkılıyor")
                            gercek_pozisyon_kapat(sym, "erken_guvenlik_cikisi")
                            continue
                    elif not durum.get("erken_kontrol_yapildi", False):
                        if ilerleme_pct < ERKEN_GUVENLIK_MIN_ILERLEME_PCT:
                            log.info(f"[ERKEN_GUVENLIK] {sym} {ERKEN_GUVENLIK_SURE_DK:.0f} dk'da "
                                     f"hâlâ ilerleme yok (%{ilerleme_pct:.2f}), erken çıkılıyor")
                            gercek_pozisyon_kapat(sym, "erken_guvenlik_cikisi")
                            continue
                        else:
                            with state_lock:
                                if sym in trade_state:
                                    trade_state[sym]["erken_kontrol_yapildi"] = True
                            durumu_diske_yaz()

                if TREND_AJANI_AKTIF:
                    son_kontrol = durum.get("son_trend_kontrol", 0)
                    if time.time() - son_kontrol >= TREND_KONTROL_ARALIGI_SN:
                        try:
                            y1d = trend_yonu(get_df(sym, "1d", MA_PERIYOT + 10))
                            y4h = trend_yonu(get_df(sym, "4h", MA_PERIYOT + 5))
                            y1h = trend_yonu(get_df(sym, "1h", MA_PERIYOT + 5))
                            bozuk_sayisi = sum(1 for y in (y1d, y4h, y1h) if y != aranan_yon)
                            tam_ters = bozuk_sayisi >= 2
                            kismi_ters = bozuk_sayisi == 1

                            with state_lock:
                                if sym not in trade_state:
                                    continue
                                trade_state[sym]["son_trend_kontrol"] = time.time()
                                if tam_ters:
                                    trade_state[sym]["ters_trend_sayisi"] = trade_state[sym].get("ters_trend_sayisi", 0) + 1
                                    trade_state[sym]["kismi_ters_sayisi"] = 0
                                    sayac_tam = trade_state[sym]["ters_trend_sayisi"]
                                    sayac_kismi = 0
                                elif kismi_ters:
                                    trade_state[sym]["kismi_ters_sayisi"] = trade_state[sym].get("kismi_ters_sayisi", 0) + 1
                                    trade_state[sym]["ters_trend_sayisi"] = 0
                                    sayac_kismi = trade_state[sym]["kismi_ters_sayisi"]
                                    sayac_tam = 0
                                else:
                                    trade_state[sym]["ters_trend_sayisi"] = 0
                                    trade_state[sym]["kismi_ters_sayisi"] = 0
                                    sayac_tam = 0
                                    sayac_kismi = 0

                            if tam_ters and sayac_tam >= TREND_TERS_TEYIT_SAYISI:
                                tg(f"⚠️ {sym} — üst trend ÇOĞUNLUKLA bozuldu, kapatılıyor.")
                                gercek_pozisyon_kapat(sym, "trend_degisti")
                                continue
                            elif kismi_ters and sayac_kismi >= TREND_TERS_TEYIT_KISMI_SAYISI:
                                tg(f"⚠️ {sym} — üst trend KISMEN bozuldu, kapatılıyor.")
                                gercek_pozisyon_kapat(sym, "trend_kismi_degisti")
                                continue
                        except Exception as e:
                            log.warning(f"[TREND_KONTROL_HATA] {sym}: {e}")

                # ── v3.7 YENİ: KISMİ KÂR ALMA (SL kontrolünden ÖNCE) ──
                # Pozisyon KISMI_KAR_ESIK_PCT'e ulaştıysa (ve henüz kısmi
                # alınmadıysa), miktarın yarısı kapatılıp kalanın SL'i
                # breakeven'e çekilir. Bu, "hedefe ulaşmadan geri dönüp SL'e
                # gitme" riskini azaltmayı amaçlar.
                #
                # v4.4 GÜNCELLEME (23.09.2026, kullanıcı gözlemiyle bulundu -
                # "kasa büyüyor sonra tekrar aynı yere dönüyor"): Büyük
                # ölçekli backtest'te (136 coin/~51 gün) kısmi kâr almanın
                # YUKSELEN stratejisi için NET ZARARLI olduğu zaten
                # kanıtlanmıştı (kısmi kâr YOKKEN net +7254$, VARKEN net
                # -7785$) - ama bu bilgi canlı botun koduna hiç işlenmemişti,
                # mekanizma tüm modlara zorunlu uygulanıyordu. Sebep: bu
                # strateji "ara sıra büyük, uzun süren hareketleri yakalama"
                # gücüne dayanıyor - kısmi kâr alma bu potansiyeli daha
                # oluşmadan (%1.5'te) kesip kalanı breakeven'e çekiyor, bu da
                # tam olarak "kâr büyüyor, bot erken kilitliyor, kalan nötr/
                # hafif kayıpla kapanıyor" hissinin kaynağı. ARTIK SADECE
                # TREND modunda açılan pozisyonlara uygulanıyor - YUKSELEN
                # modunda pozisyon doğrudan tam TP ya da tam SL'e gidiyor
                # (backtest'te en kârlı kombinasyon buydu).
                if (KISMI_KAR_AKTIF and durum.get("acilis_modu", "trend") == "trend"
                        and not durum.get("kismi_alindi", False)):
                    kismi_esik_fiyat = (durum["entry"] * (1 + KISMI_KAR_ESIK_PCT) if long_mu
                                         else durum["entry"] * (1 - KISMI_KAR_ESIK_PCT))
                    kismi_esik_gecti = (guncel >= kismi_esik_fiyat) if long_mu else (guncel <= kismi_esik_fiyat)
                    if kismi_esik_gecti:
                        kismi_kar_al(sym, durum)
                        continue

                sl_tetiklendi = (guncel <= durum["sl"]) if long_mu else (guncel >= durum["sl"])
                if sl_tetiklendi:
                    gercek_pozisyon_kapat(sym, "sl")
                    continue

                tp = durum.get("tp")
                if tp is None:
                    log.warning(f"[ESKI_POZISYON] {sym} 'tp' alanı yok (v3.0 öncesi kalıntı olabilir) - güvenlik amaçlı kapatılıyor")
                    gercek_pozisyon_kapat(sym, "eski_format_guvenlik_kapanisi")
                    continue
                tp_tetiklendi = (guncel >= tp) if long_mu else (guncel <= tp)
                if tp_tetiklendi:
                    gercek_pozisyon_kapat(sym, "hizli_tp")
                    continue

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


def izleme_listesi_guncelle():
    if time.time() - _son_izleme_taramasi["ts"] < IZLEME_TARAMA_ARALIGI_SN:
        return
    _son_izleme_taramasi["ts"] = time.time()

    try:
        genis_liste = genis_evren_listesi()
    except Exception as e:
        log.warning(f"[IZLEME_TARAMA] {e}")
        return

    with izleme_lock:
        mevcut = set(izleme_listesi.keys())
    with state_lock:
        acik = set(trade_state.keys())

    adaylar = [s for s in genis_liste if s not in mevcut and s not in acik and not cooldown_da_mi(s)]
    if not adaylar:
        return

    eklenen = 0
    with ThreadPoolExecutor(max_workers=6) as havuz:
        gelecekler = {havuz.submit(iki_uzerinden_uc_kontrol, sym): sym for sym in adaylar}
        for gelecek in as_completed(gelecekler):
            sym = gelecekler[gelecek]
            try:
                uyumlu = gelecek.result()
            except Exception as e:
                log.warning(f"[IZLEME_KONTROL] {sym}: {e}")
                continue
            if not uyumlu:
                continue
            with izleme_lock:
                if sym in izleme_listesi:
                    continue
                if len(izleme_listesi) >= IZLEME_LISTESI_BOYUTU:
                    en_eski = min(izleme_listesi.items(), key=lambda kv: kv[1]["eklenme_zamani"])
                    izleme_listesi.pop(en_eski[0], None)
                izleme_listesi[sym] = {"eklenme_zamani": time.time()}
                eklenen += 1
    if eklenen:
        log.info(f"[IZLEME_LISTESI] {eklenen} yeni coin eklendi, liste boyutu={len(izleme_listesi)}")


def izleme_listesi_kontrol():
    with izleme_lock:
        izlenenler = dict(izleme_listesi)
    if not izlenenler:
        return 0

    acilanlar = 0
    for sym, kayit in izlenenler.items():
        with state_lock:
            if sym in trade_state or len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
                continue
        if cooldown_da_mi(sym):
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            continue

        yas_saat = (time.time() - kayit["eklenme_zamani"]) / 3600
        if yas_saat > IZLEME_MAX_YAS_SAAT:
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            log.info(f"[IZLEME_LISTESI] {sym} bayatladı ({yas_saat:.1f}sa), listeden çıkarıldı")
            continue

        try:
            sinyal = ucyon_sinyal(sym)
        except Exception as e:
            log.warning(f"[IZLEME_SINYAL] {sym}: {e}")
            continue

        if sinyal and not OTOMATIK_GIRIS_AKTIF:
            continue    # v6.1: otomatik giriş kapalı, izleme listesi sinyali görmezden gel (pozisyon açma)
        if sinyal:
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            with state_lock:
                if sym in trade_state or len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
                    continue
            log.info(f"[IZLEME_LISTESI] {sym} tam uyuma ulaştı (1D+4H+1H+15m+hacim+pump), pozisyon açılıyor")
            gercek_pozisyon_ac(sinyal)
            acilanlar += 1
        else:
            try:
                if not iki_uzerinden_uc_kontrol(sym):
                    with izleme_lock:
                        izleme_listesi.pop(sym, None)
            except Exception:
                pass
    return acilanlar


def tarama_loop():
    tg(f"⚡ LIVE BOT v7.2 (MANUEL ONAY PANELİ + WEB PANELİ + OTOMATİK BİLDİRİM + ANİ HAREKET) başladı — GERÇEK PARA\n"
       f"🎛️ Otomatik giriş: {'AÇIK' if OTOMATIK_GIRIS_AKTIF else 'KAPALI (varsayılan) — /tara ile aday bul, ✅ Aç ile onayla'}\n"
       f"🎯 Şu anki aktif mod: {aktif_strateji_modu().upper()}\n"
       f"MAX_POS={MAX_POS} | Marjin: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i (taban ${MARJIN_TABAN_USDT:.2f}, tavan ${MARJIN_TAVAN_USDT:.2f}), {LEV}x\n"
       f"Giriş: 1D+4H+1H uyum + hacim teyidi (x{HACIM_TEYIT_KATSAYI:.1f}) + pump filtresi (%{PUMP_FILTRE_ESIK_PCT:.0f} üstü reddedilir)\n"
       + (f"⚡ ÇIKIŞ (YUKSELEN): SL %{YUKSELEN_SL_PCT*100:.1f}, kâr %{YUKSELEN_TRAILING_AKTIVASYON_PCT*100:.1f}'e "
          f"ulaşınca iz sürme (zirveden %{YUKSELEN_TRAILING_PAYI_PCT*100:.1f} geride), "
          f"{'sabit hedef %'+format(YUKSELEN_HEDEF_PCT*100,'.1f') if YUKSELEN_TP_TAVAN_AKTIF else 'hedef tavanı YOK'}, kısmi kâr alma KAPALI\n"
          if aktif_strateji_modu() == "yukselen" else
          f"⚡ ÇIKIŞ: %{KISMI_KAR_ESIK_PCT*100:.1f}'te kısmi kâr al (%{KISMI_KAR_ORANI*100:.0f}) + breakeven, "
          f"tam hedef %{HIZLI_HEDEF_PCT*100:.1f} - iz sürme YOK\n"
          f"SL taban %{MIN_SL_PCT*100:.0f}\n")
       + f"Max tutma: {MAX_HOLD_SAAT:.0f} saat\n"
       f"🔄 Trend dönüş ajanı: {'AKTİF' if TREND_AJANI_AKTIF else 'KAPALI (kullanıcı kararı)'}\n"
       f"🌡️ Temkinli mod: {'AKTİF' if TEMKINLI_MOD_AKTIF else 'KAPALI'} "
       f"(BTC düşerse MAX_POS yarıya iner, trend gücü eşiği %{MIN_4H_TREND_GUCU_PCT_TEMKINLI:.1f}'e yükselir - "
       f"BTC'den bağımsız güçlü coinler yine geçebilir)\n"
       f"👁️ İzleme listesi ajanı: max {IZLEME_LISTESI_BOYUTU} coin, {IZLEME_TARAMA_ARALIGI_SN//60}dk'da bir genişletiliyor\n\n"
       f"📌 v6.2: web paneli (WEB_PANEL_SIFRE ile korumalı), /tara (4S+1S analiz + renkli kart + Aç/Düzenle/Geç), /ac SEMBOL yon giriş sl tp [marjin], "
       f"/pozisyonlar (Kapat/İptal), /durdur ve /baslat (otomatik giriş). Varsayılan marjin ${MANUEL_MARJIN_VARSAYILAN_USDT:.0f} "
       f"(Düzenle ya da /ac'te değiştirilebilir). Eski otomatik strateji: hisse/ETF {'DAHİL' if RWA_HISSE_DAHIL else 'dışlandı'}, "
       f"kovalama koruması (%{KOVALAMA_MAX_PCT:.1f}), aynı mumdan en fazla {AYNI_MUM_MAX_GIRIS} giriş, günlük zarar freni (%{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}), /surtunme. "
       f"iz sürme stop teşhisi. Eşikler geçmiş veriye dayanır, canlıda henüz doğrulanmadı.\n\n"
       f"📱 /panel yaz — tam menüyü görürsün.")

    baslangic_uzlastirma()

    while True:
        try:
            # v5.6: günlük zarar freni - yeni giriş açmadan önce kontrol (açık pozisyonlar manage_loop'ta yönetilir)
            fren, gun_pnl, gun_basi = gunluk_zarar_freni_mi()
            if fren:
                bugun = time.strftime("%Y-%m-%d", time.gmtime())
                if _frene_bildirim["gun"] != bugun:
                    _frene_bildirim["gun"] = bugun
                    tg(f"🛑 GÜNLÜK ZARAR FRENİ devrede: bugün gerçekleşen ≈{gun_pnl:+.2f}$ "
                       f"(gün başı ≈{gun_basi:.2f}$'ın %{abs(gun_pnl)/gun_basi*100:.1f}'i, limit %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}). "
                       f"UTC 00:00'a kadar YENİ işlem açılmayacak, açık pozisyonlar yönetilmeye devam eder.")
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            emp = efektif_max_pos()
            with state_lock:
                bos_slot = emp - len(trade_state) - len(acilis_rezervasyonlari)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            try:
                if aktif_strateji_modu() == "trend":
                    izleme_listesi_guncelle()
                    izleme_acilan = izleme_listesi_kontrol()
                else:
                    izleme_acilan = 0  # v4.0: yükselen modunda izleme listesi (1D+4H+1H bazlı) anlamsız
            except Exception as e:
                log.warning(f"[IZLEME_GENEL] {e}")
                izleme_acilan = 0

            emp = efektif_max_pos()
            with state_lock:
                bos_slot = emp - len(trade_state) - len(acilis_rezervasyonlari)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            mod_simdi = aktif_strateji_modu()
            adaylar = yukselen_coin_havuzu() if mod_simdi == "yukselen" else aday_havuzu()
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
                    gelecekler = {havuz.submit(ucyon_sinyal, sym): sym for sym in taranacaklar}
                    for gelecek in as_completed(gelecekler):
                        sym = gelecekler[gelecek]
                        try:
                            sinyal = gelecek.result()
                        except Exception as e:
                            log.warning(f"[TARAMA] {sym}: {e}")
                            continue
                        if sinyal and OTOMATIK_GIRIS_AKTIF:
                            with state_lock:
                                if sym in trade_state or len(trade_state) + len(acilis_rezervasyonlari) >= efektif_max_pos():
                                    continue
                            gercek_pozisyon_ac(sinyal)
                            bulunan += 1

            with izleme_lock:
                izleme_boyut = len(izleme_listesi)
            log.info(f"[NABIZ] tur tamam | havuz={len(adaylar)} | bulunan={bulunan} | "
                     f"izleme_acilan={izleme_acilan} | izleme_liste={izleme_boyut}/{IZLEME_LISTESI_BOYUTU} | "
                     f"acik={emp-bos_slot}/{emp} (max_pos_normal={MAX_POS})")
            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


if __name__ == "__main__":
    etiket = "AÇIK" if OTOMATIK_GIRIS_AKTIF else "KAPALI"
    print(f"LIVE BOT v7.2 (MANUEL ONAY PANELİ + WEB PANELİ + OTOMATİK BİLDİRİM + ANİ HAREKET, otomatik giriş {etiket}) BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    bloke_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=manuel_limit_loop, daemon=True).start()
    threading.Thread(target=otomatik_bildirim_loop, daemon=True).start()
    threading.Thread(target=ani_hareket_loop, daemon=True).start()
    threading.Thread(target=web_panel_baslat, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
