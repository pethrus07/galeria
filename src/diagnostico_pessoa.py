"""Por que uma pessoa some: falta de foto no acervo ou falta de reconhecimento?

Mês a mês: fotos de câmera no acervo, fotos com rosto, fotos com a pessoa, e
rostos não atribuídos com alguma semelhança (cos >= 0.30) com o centro dela.

  python diagnostico_pessoa.py <nome> <desde AAAA-MM>
"""
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np

from imagens import BANCO

nome, desde = sys.argv[1], sys.argv[2]
db = sqlite3.connect(BANCO)
pid = db.execute("select id from pessoas where nome=? order by n desc", (nome,)).fetchone()[0]
rostos = db.execute("""select r.id, r.midia_id, r.pessoa, r.emb, r.conf, r.area, m.data
                       from rostos r join midia m on m.id = r.midia_id""").fetchall()
E = {r[0]: np.frombuffer(r[3], dtype=np.float32) for r in rostos}
centro = np.mean([E[r[0]] for r in rostos if r[2] == pid], axis=0)
centro /= np.linalg.norm(centro)

mes = lambda ts: datetime.fromtimestamp(ts).strftime("%Y-%m")
acervo = defaultdict(int)
for (ts,) in db.execute("""select m.data from midia m join classificacao c on c.midia_id = m.id
                           where m.fonte_imagem in ('camera','digitalizada')"""):
    acervo[mes(ts)] += 1
com_rosto, com_ela, parecidos = defaultdict(set), defaultdict(set), defaultdict(set)
for r in rostos:
    m = mes(r[6])
    com_rosto[m].add(r[1])
    if r[2] == pid:
        com_ela[m].add(r[1])
    elif r[2] is None and float(E[r[0]] @ centro) >= 0.30:
        parecidos[m].add(r[1])

print("mês      câmera  c/rosto  c/ela  parecidos-soltos")
for m in sorted(k for k in acervo if k >= desde):
    print(f"{m}  {acervo[m]:>6}  {len(com_rosto[m]):>7}  {len(com_ela[m]):>5}  {len(parecidos[m]):>6}")
