"""Dá nome a uma pessoa pelo terminal (o mesmo que a aba Pessoas faz).

  python nomear.py <pessoa_id> <nome> [rosto_id ...]   # rostos avulsos entram junto
  python nomear.py --rostos <nome> <rosto_id ...>       # só rostos avulsos
"""
import sqlite3
import sys

from imagens import BANCO

db = sqlite3.connect(BANCO)
args = sys.argv[1:]
if args[0] == "--rostos":
    nome, extras = args[1], [int(a) for a in args[2:]]
    rostos = []
else:
    pid, nome, extras = int(args[0]), args[1], [int(a) for a in args[2:]]
    rostos = [r[0] for r in db.execute("select id from rostos where pessoa=?", (pid,))]
db.executemany("insert or replace into rosto_nome values (?,?)", [(r, nome) for r in rostos + extras])
db.commit()
print(f"{nome}: {len(rostos)} rostos do grupo + {len(extras)} avulsos")
