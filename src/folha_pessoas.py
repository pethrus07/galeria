"""Folha das pessoas: uma linha por pessoa, com 8 rostos de fotos diferentes.

  python folha_pessoas.py saida.jpg [n_pessoas]
"""
import sqlite3
import sys

from PIL import Image, ImageDraw

from imagens import BANCO, carregar

LADO = 110


def main() -> None:
    saida = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    db = sqlite3.connect(BANCO)
    pessoas = db.execute("select id, n from pessoas order by n desc limit ?", (n,)).fetchall()
    folha = Image.new("RGB", (LADO * 9, LADO * len(pessoas)), "white")
    d = ImageDraw.Draw(folha)
    for lin, (pid, qtd) in enumerate(pessoas):
        d.text((6, lin * LADO + 40), f"pessoa {pid}\n{qtd} fotos", fill="black")
        rostos = db.execute("""
            select r.x1, r.y1, r.x2, r.y2, m.caminho, m.tipo from rostos r join midia m on m.id = r.midia_id
            where r.pessoa = ? group by r.midia_id order by random() limit 8""", (pid,)).fetchall()
        for col, (x1, y1, x2, y2, cam, tipo) in enumerate(rostos, 1):
            arr = carregar(cam, tipo)
            if arr is None:
                continue
            img = Image.fromarray(arr)
            w, h = img.size
            m = 0.25 * (x2 - x1)
            recorte = img.crop((max(0, (x1 - m) * w), max(0, (y1 - m) * h),
                                min(w, (x2 + m) * w), min(h, (y2 + m) * h))).resize((LADO - 4, LADO - 4))
            folha.paste(recorte, (col * LADO + 2, lin * LADO + 2))
    folha.save(saida, quality=85)
    print(saida)


if __name__ == "__main__":
    main()
