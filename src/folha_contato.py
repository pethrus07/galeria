"""Folha de contato para conferir a análise: miniaturas com os sinais da IA.

  python folha_contato.py saida.jpg [sql_where] [limite]
"""
import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps
from pillow_heif import register_heif_opener

from imagens import BANCO, carregar

register_heif_opener()
LADO, COLS = 240, 6


def main() -> None:
    saida = sys.argv[1]
    onde = sys.argv[2] if len(sys.argv) > 2 else "1=1"
    limite = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    db = sqlite3.connect(BANCO)
    linhas = db.execute(f"""
        select m.id, m.caminho, m.tipo, s.cena1, s.cena2, s.estetica, s.nitidez, s.n_rostos
        from sinais s join midia m on m.id = s.midia_id where {onde}
        order by s.estetica desc limit {limite}""").fetchall()
    rows = (len(linhas) + COLS - 1) // COLS
    folha = Image.new("RGB", (COLS * LADO, rows * (LADO + 34)), "white")
    d = ImageDraw.Draw(folha)
    for i, (mid, cam, tipo, c1, c2, est, nit, nr) in enumerate(linhas):
        arr = carregar(cam, tipo)
        x, y = (i % COLS) * LADO, (i // COLS) * (LADO + 34)
        if arr is not None:
            img = ImageOps.contain(Image.fromarray(arr), (LADO - 4, LADO - 4))
            folha.paste(img, (x + 2, y + 2))
        d.text((x + 3, y + LADO), f"#{mid} {c1}/{c2}", fill="black")
        d.text((x + 3, y + LADO + 14), f"est {est:.1f}  nit {nit:.1f}  rostos {nr}", fill="black")
    folha.save(saida, quality=85)
    print(saida, len(linhas))


if __name__ == "__main__":
    main()
