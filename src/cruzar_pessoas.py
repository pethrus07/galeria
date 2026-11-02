"""Cruza pessoas com datas: período, fotos por mês e com quem aparece junto.

  python cruzar_pessoas.py [n_pessoas]
"""
import sqlite3
import sys
from collections import Counter

import numpy as np

from imagens import BANCO

n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
db = sqlite3.connect(BANCO)

top = [r[0] for r in db.execute("select id from pessoas order by n desc limit ?", (n,))]
fotos = {p: {r[0]: r[1] for r in db.execute("""
            select distinct r.midia_id, m.data from rostos r join midia m on m.id = r.midia_id
            where r.pessoa = ?""", (p,))} for p in top}

print("pessoa  fotos  primeira    última      fotos por ano")
for p in top:
    datas = sorted(fotos[p].values())
    anos = Counter(np.datetime64(d, "s").astype("datetime64[Y]").astype(str) for d in datas)
    ini, fim = (np.datetime64(datas[i], "s").astype("datetime64[D]") for i in (0, -1))
    print(f"{p:>6} {len(datas):>6}  {ini}  {fim}  {dict(sorted(anos.items()))}")

print("\naparecem juntos (mesma foto):")
for i, a in enumerate(top):
    for b in top[i + 1:]:
        k = len(fotos[a].keys() & fotos[b].keys())
        if k >= 5:
            print(f"  {a} + {b}: {k}")

# rostos parecidos com cada uma das 2 maiores pessoas que ficaram de fora dos grupos
print("\nrostos fora de grupo parecidos (cos >= 0.45) com o centro de cada pessoa:")
todos = db.execute("select id, pessoa, emb from rostos").fetchall()
E = {r[0]: np.frombuffer(r[2], dtype=np.float32) for r in todos}
for p in top[:6]:
    membros = [r[0] for r in todos if r[1] == p]
    centro = np.mean([E[i] for i in membros], axis=0)
    centro /= np.linalg.norm(centro)
    soltos = [r[0] for r in todos if r[1] is None and float(E[r[0]] @ centro) >= 0.45]
    print(f"  pessoa {p}: {len(soltos)} rostos soltos parecidos")
