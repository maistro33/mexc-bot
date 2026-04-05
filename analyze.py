import json
import pandas as pd

with open("memory.json") as f:
    data = json.load(f)

df = pd.DataFrame(data)

print("Toplam Trade:", len(df))
print("Win Rate:", (df["result"] > 0).mean())
print("Ortalama PNL:", df["result"].mean())

print("\nTREND:")
print(df.groupby(df["trend"] > 0)["result"].mean())

print("\nVOLUME:")
print(df.groupby(df["volume_spike"] > 1.5)["result"].mean())

print("\nFAKE:")
print(df.groupby("fake")["result"].mean())
