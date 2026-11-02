"""Folha dos rostos soltos parecidos com uma pessoa, do mais ao menos parecido.

  python folha_parecidos.py <pessoa_id> saida.jpg [cos_min]
"""
import sqlite3
import sys

import numpy as np
from PIL import Image, ImageDraw

from imagens import BANCO, carregar

LADO, COLS = 120, 10


def main() -> None:
    pid, saida = int(sys.argv[1]), sys.argv[2]
    cmin = float(sys.argv[3]) if len(sys.argv) > 3 else 0.45
    db = sqlite3.connect(BANCO)
    todos = db.execute("""select r.id, r.pessoa, r.emb, r.x1, r.y1, r.x2, r.y2, m.caminho, m.tipo
                          from rostos r join midia m on m.id = r.midia_id""").fetchall()
    E = {r[0]: np.frombuffer(r[2], dtype=np.float32) for r in todos}
    centro = np.mean([E[r[0]] for r in todos if r[1] == pid], axis=0)
    centro /= np.linalg.norm(centro)
    soltos = sorted(((float(E[r[0]] @ centro), r) for r in todos
                     if r[1] is None and float(E[r[0]] @ centro) >= cmin), key=lambda x: -x[0])
    linhas = (len(soltos) + COLS - 1) // COLS
    folha = Image.new("RGB", (COLS * LADO, max(1, linhas) * (LADO + 16)), "white")
    d = ImageDraw.Draw(folha)
    for i, (cos, r) in enumerate(soltos):
        arr = carregar(r[7], r[8])
        x, y = (i % COLS) * LADO, (i // COLS) * (LADO + 16)
        if arr is not None:
            img = Image.fromarray(arr)
            w, h = img.size
            m = 0.25 * (r[5] - r[3])
            img = img.crop((max(0, (r[3] - m) * w), max(0, (r[4] - m) * h),
                            min(w, (r[5] + m) * w), min(h, (r[6] + m) * h))).resize((LADO - 4, LADO - 4))
            folha.paste(img, (x + 2, y + 2))
        d.text((x + 3, y + LADO), f"#{r[0]} {cos:.2f}", fill="black")
    folha.save(saida, quality=85)
    print(saida, len(soltos))


if __name__ == "__main__":
    main()
