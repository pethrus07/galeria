"""Mostra onde a revisão está: decisões gravadas, por destino, e pessoas com nome."""
import sqlite3

from imagens import BANCO

db = sqlite3.connect(BANCO)
q = lambda s: db.execute(s).fetchall()
print("decisões:", q("select decisao, count(*) from decisoes group by 1 order by 2 desc"))
print("decididas:", q("select count(*) from decisoes")[0][0], "de", q("select count(*) from classificacao")[0][0])
print("por destino sugerido (decididas, total):",
      q("""select c.destino, count(d.midia_id), count(*) from classificacao c
           left join decisoes d on d.midia_id = c.midia_id group by 1"""))
print("pessoas com nome:", q("select id, n, nome from pessoas where nome is not null order by n desc"))
print("período:", q("""select datetime(min(quando), 'unixepoch', 'localtime'),
                              datetime(max(quando), 'unixepoch', 'localtime') from decisoes"""))
