"""Linha do tempo de uma pessoa: momentos em que ela aparece, mês a mês.

Conta o momento inteiro (lugares e paisagens do mesmo passeio entram),
fora o que já foi decidido como lixo.

  python linha_do_tempo.py <nome>
"""
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

from imagens import BANCO

nome = sys.argv[1]
db = sqlite3.connect(BANCO)
pid = db.execute("select id from pessoas where nome=? order by n desc", (nome,)).fetchone()[0]

momentos = db.execute("""
    select mo.id, mo.inicio, mo.fim, mo.cidade, mo.cena, mo.pessoas,
           sum(json_each.value = ?) > 0 as com_ela
    from momentos mo, json_each(mo.pessoas)
    group by mo.id having com_ela""", (pid,)).fetchall()
ids = [m[0] for m in momentos]
fotos = dict(db.execute(f"""
    select c.momento_id, count(*) from classificacao c left join decisoes d on d.midia_id = c.midia_id
    where c.momento_id in ({','.join('?' * len(ids))})
      and coalesce(d.decisao, c.destino) in ('manter', 'galeria', 'destaque')
    group by 1""", ids).fetchall())
com_ela = dict(db.execute(f"""
    select c.momento_id, count(distinct r.midia_id) from rostos r join classificacao c on c.midia_id = r.midia_id
    where r.pessoa = ? group by 1""", (pid,)).fetchall())

por_mes = defaultdict(list)
for m in momentos:
    por_mes[datetime.fromtimestamp(m[1]).strftime("%Y-%m")].append(m)

total_fotos = sum(fotos.get(i, 0) for i in ids)
print(f"{nome}: {len(momentos)} momentos, {total_fotos} fotos boas nesses momentos")
print(f"de {datetime.fromtimestamp(min(m[1] for m in momentos)):%d/%m/%Y} "
      f"a {datetime.fromtimestamp(max(m[1] for m in momentos)):%d/%m/%Y}\n")
for mes in sorted(por_mes):
    ms = por_mes[mes]
    n = sum(fotos.get(m[0], 0) for m in ms)
    grandes = sorted(ms, key=lambda m: -fotos.get(m[0], 0))[:3]
    destaque = ", ".join(f"{datetime.fromtimestamp(m[1]):%d/%m} {m[4]}"
                         f"{' em ' + m[3].split(',')[0] if m[3] else ''} ({fotos.get(m[0], 0)})" for m in grandes)
    print(f"{mes}  {len(ms):>3} momentos  {n:>4} fotos   maiores: {destaque}")
