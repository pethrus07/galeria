"""Marca cópias que o sha256 não pega (mesma foto com bytes diferentes).

O Google Fotos em "economia de espaço" recomprime: a foto do celular e a do
Takeout são a mesma, mas os bytes mudam. Aqui a cópia é: mesmo phash (até 4
bits de diferença) e tirada no mesmo instante (até 5 s); vídeo: mesma duração
(±0,5 s) e mesmo instante. A mais antiga no banco fica como original.
"""
import sqlite3
from collections import defaultdict

from imagens import BANCO

LIMITE_BITS, LIMITE_SEG = 4, 5


def bits(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def main() -> None:
    db = sqlite3.connect(BANCO)
    if "copia_de" not in {c[1] for c in db.execute("pragma table_info(midia)")}:
        db.execute("alter table midia add column copia_de integer")
    # um representante por sha256; cópias exatas já se resolvem pelo sha
    linhas = db.execute("""
        select id, tipo, data, phash, duracao from midia
        where id in (select min(id) from midia where erro is null group by sha256)
        order by id""").fetchall()
    por_segundo = defaultdict(list)
    marcadas = 0
    for mid, tipo, data, phash, dur in linhas:
        achou = None
        for s in range(data - LIMITE_SEG, data + LIMITE_SEG + 1):
            for oid, otipo, ophash, odur in por_segundo.get(s, ()):
                if otipo != tipo:
                    continue
                if tipo == "foto" and phash and ophash and bits(phash, ophash) <= LIMITE_BITS:
                    achou = oid
                elif tipo == "video" and dur and odur and abs(dur - odur) <= 0.5:
                    achou = oid
                if achou:
                    break
            if achou:
                break
        if achou:
            db.execute("update midia set copia_de=? where id=?", (achou, mid))
            marcadas += 1
        else:
            por_segundo[data].append((mid, tipo, phash, dur))
    db.commit()
    print(f"cópias por semelhança: {marcadas}")
    print("por origem:", db.execute("""select origem, count(*) from midia where copia_de is not null
                                       group by 1""").fetchall())


if __name__ == "__main__":
    main()
