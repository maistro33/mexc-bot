# Walk-forward: veri 4 aya bölünür. Her ay için ayar SADECE önceki aylarda seçilir, o ayda sınanır.
# Ayrıca: önceden sabitlenmiş ayarların (botta çalışan) her ay sonucu.
import sys, time, itertools, json, numpy as np
sys.path.insert(0, ".")
from lab import yukle, evren_hazirla, simule, ozet
import strat as st

t = time.time()
d = yukle("veri"); evren_hazirla(d); st.uclu_hazirla(d); st.patlama_hazirla(d)
print(f"veri: {len(d['S'])} coin, {d['C'].shape[1]} mum ({d['C'].shape[1] / 96:.0f} gün) · hazırlık {time.time() - t:.0f} sn", flush=True)
L = d["C"].shape[1]; B = [200 + (L - 200) * q // 4 for q in range(5)]
ay = lambda q: time.strftime("%d.%m", time.gmtime(d["T"][B[q]] / 1000)) + "–" + time.strftime("%d.%m", time.gmtime(d["T"][B[q + 1] - 1] / 1000))
print("dönemler:", [ay(q) for q in range(4)], flush=True)

def donemler(sinyal, **kw):
    return [ozet(simule(d, sinyal, B[q], B[q + 1], **kw)) for q in range(4)]

def wf(ad, izgara):
    """izgara: [(etiket, sinyal_fn, kw)] — her ay için önceki ayların toplamına göre en iyi ayarı seç."""
    R = []
    for et, f, kw in izgara:
        R.append((et, donemler(f, **kw)))
    oos = []
    for q in range(1, 4):
        en = max(R, key=lambda r: sum(x["top"] for x in r[1][:q]))
        oos.append((ay(q), en[0], en[1][q]))
    toplam = sum(o[2]["top"] for o in oos)
    print(f"\n=== {ad} — {len(R)} ayar ===", flush=True)
    for q, et, o in oos: print(f"  {q}: seçilen [{et}] → {o['n']} işlem, {o['top']:+.1f} $, %{o['kaz']} kazanan, düşüş {o['dd']}", flush=True)
    print(f"  GÖRMEDİĞİ 3 AYIN TOPLAMI: {toplam:+.1f} $", flush=True)
    artilar = sum(1 for r in R if all(x["top"] > 0 for x in r[1]))
    print(f"  (bilgi: 4 ayın dördünde de artı olan ayar sayısı: {artilar}/{len(R)})", flush=True)
    return toplam, R

sonuc = {}
# 0) Botta şu an çalışan Üçlü Onay — sabit ayar, seçim yok
f = st.uclu(d, 0.10); r = donemler(f, sl=0.08, tpa=0.01, maxbar=24, yon_max=5, top_max=10)
print("\n=== Üçlü Onay (botta çalışan ayar, seçim YOK) ===")
for q in range(4): print(f"  {ay(q)}: {r[q]}")
print(f"  TOPLAM: {sum(x['top'] for x in r):+.1f} $", flush=True)

# 1) Üçlü onay ızgarası
iz = []
for thr, sl, tpa, mb in itertools.product((0.05, 0.10, 0.20), (0.04, 0.08), (0.01, 0.02), (16, 48)):
    iz.append((f"2g%{thr * 100:g} sl%{sl * 100:g} tp%{tpa * 100:g} {mb // 4}sa", st.uclu(d, thr), dict(sl=sl, tpa=tpa, maxbar=mb)))
sonuc["uclu"] = wf("🎯 Üçlü Onay", iz)[0]

# 2) Ani patlama (15 dk mum)
iz = []
for hm, vk, sl, tpa in itertools.product((0.03, 0.05), (3.0, 5.0), (0.025, 0.05), (0.015, 0.03)):
    iz.append((f"%{hm * 100:g} hacim{vk:g}× sl%{sl * 100:g} tp%{tpa * 100:g}", st.patlama(d, hm, vk), dict(sl=sl, tpa=tpa, maxbar=8)))
sonuc["patlama"] = wf("⚡ Ani patlama (15 dk)", iz)[0]

# 3) Ters patlama — hareketin dönmesine oyna (aynı sinyal, ters yön)
def ters(f): return lambda i: [(k, -u) for k, u in f(i)]
iz = []
for hm, vk, sl, tpa in itertools.product((0.03, 0.05), (3.0, 5.0), (0.025, 0.05), (0.015, 0.03)):
    iz.append((f"TERS %{hm * 100:g} hacim{vk:g}× sl%{sl * 100:g} tp%{tpa * 100:g}", ters(st.patlama(d, hm, vk)), dict(sl=sl, tpa=tpa, maxbar=8)))
sonuc["ters"] = wf("🔄 Ters patlama", iz)[0]

# 4) Merdiven
st.merdiven_hazirla(d)
iz = []
for mr, tpa in itertools.product((0.02, 0.03, 0.05), (0.015, 0.03, 1.0)):
    iz.append((f"merdiven stop≤%{mr * 100:g} tp%{tpa * 100:g}", st.merdiven(d, mr), dict(sl=0.20, tpa=tpa, maxbar=48, lag=2)))
# merdivende stop = son dip (iz fonksiyonu) — simule'ye iz ile
R = []
for et, f, kw in iz:
    R.append((et, [ozet(simule(d, f, B[q], B[q + 1], iz=st.merdiven_iz(d), **kw)) for q in range(4)]))
oos = []
for q in range(1, 4):
    en = max(R, key=lambda r: sum(x["top"] for x in r[1][:q])); oos.append((ay(q), en[0], en[1][q]))
print(f"\n=== 🪜 Merdiven — {len(R)} ayar ===")
for q, et, o in oos: print(f"  {q}: seçilen [{et}] → {o['n']} işlem, {o['top']:+.1f} $, %{o['kaz']} kazanan, düşüş {o['dd']}")
sonuc["merdiven"] = sum(o[2]["top"] for o in oos); print(f"  GÖRMEDİĞİ 3 AYIN TOPLAMI: {sonuc['merdiven']:+.1f} $", flush=True)

print("\nÖZET (görmediği 3 ay):", {k: round(v, 1) for k, v in sonuc.items()}, f"· süre {time.time() - t:.0f} sn")
