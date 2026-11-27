import sys,itertools,time;sys.path.insert(0,'.')
from lab import *;import strat as st
t=time.time();d=yukle('veri');evren_hazirla(d);st.uclu_hazirla(d);L=d['C'].shape[1];B=[200+(L-200)*q//4 for q in range(5)]
F={thr:st.uclu(d,thr) for thr in (0.10,0.20)}
R=[]
for thr,gr,gw,sl,tpa in itertools.product((0.10,0.20),(0.02,0.03,0.04,0.05),(8,16,32),(0.08,0.15),(0.01,0.02)):
    r=[ozet(simule(d,F[thr],B[q],B[q+1],sl=sl,tpa=tpa,maxbar=24,geri=gr,gw=gw)) for q in range(4)]
    R.append(((thr,gr,gw,sl,tpa),r))
print(len(R),"ayar",round(time.time()-t),"sn",flush=True)
et=lambda k:f"2g%{k[0]*100:g} geri%{k[1]*100:g} {k[2]*15}dk sl%{k[3]*100:g} tp%{k[4]*100:g}"
print("\nWALK-FORWARD (ayar sadece önceki aylarda seçilir):")
oos=0
for q in range(1,4):
    en=max(R,key=lambda x:sum(y['top'] for y in x[1][:q]));o=en[1][q];oos+=o['top']
    print(f"  ay {q+1}: seçilen [{et(en[0])}] (önceki aylar {sum(y['top'] for y in en[1][:q]):+.1f}) → GÖRMEDİĞİ ay: {o['n']} işlem, {o['top']:+.1f} $, %{o['kaz']}")
print(f"  GÖRMEDİĞİ 3 AY TOPLAM: {oos:+.1f} $")
print("\n4 ayın dördünde de artı:",[(et(k),[y['top'] for y in r]) for k,r in R if all(y['top']>0 for y in r)])
R.sort(key=lambda x:-sum(y['top'] for y in x[1]))
print("\nen iyi 5 (4 ay toplam — bilgi amaçlı, seçim yanlılığı var):")
for k,r in R[:5]: print(" ",et(k),round(sum(y['top'] for y in r),1),[y['top'] for y in r])
print("artı olan ayar:",sum(1 for k,r in R if sum(y['top'] for y in r)>0),"/",len(R))
