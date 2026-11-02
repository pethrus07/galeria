"""Marca de onde a imagem veio: câmera, print ou baixada (lê só o cabeçalho EXIF).

  digitalizada → está em entrada/digitalizadas (foto de papel escaneada)
  camera  → tem fabricante/modelo no EXIF, ou nome de câmera (20240421_144049, IMG_, PXL_, VID_)
  print   → nome de screenshot, ou PNG sem EXIF no tamanho de tela de celular
  baixada → o resto (WhatsApp, internet, redes sociais, arte)
"""
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from imagens import BANCO

register_heif_opener()

NOME_CAMERA = re.compile(r"^(IMG|PXL|VID|DSC|MVIMG)?[_-]?20\d{6}[_-]\d{6}|^(IMG|PXL|DSC|VID)_\d+", re.I)
NOME_PRINT = re.compile(r"screenshot|captura|screen_?record|print", re.I)
NOME_WHATS = re.compile(r"^(IMG|VID)-\d{8}-WA\d+|whatsapp", re.I)


def origem_imagem(linha) -> tuple[int, str, str | None]:
    mid, caminho, tipo, largura, altura = linha
    nome = Path(caminho).name
    marca = None
    if tipo == "foto":
        try:
            with Image.open(caminho) as img:
                ex = img.getexif()
                marca = " ".join(str(ex.get(t, "")).strip("\x00 ") for t in (0x010F, 0x0110)).strip() or None
        except Exception:
            pass
    if "digitalizadas" in Path(caminho).parts:
        return mid, "digitalizada", marca
    if NOME_PRINT.search(nome):
        return mid, "print", marca
    if NOME_WHATS.search(nome):
        return mid, "whatsapp", marca
    if marca or NOME_CAMERA.search(nome):
        return mid, "camera", marca
    return mid, "baixada", marca


def main() -> None:
    db = sqlite3.connect(BANCO)
    cols = {c[1] for c in db.execute("pragma table_info(midia)")}
    for c in ("fonte_imagem", "camera"):
        if c not in cols:
            db.execute(f"alter table midia add column {c} text")
    linhas = db.execute("select id, caminho, tipo, largura, altura from midia").fetchall()
    with ThreadPoolExecutor(8) as pool:
        for mid, fonte, marca in pool.map(origem_imagem, linhas):
            db.execute("update midia set fonte_imagem=?, camera=? where id=?", (fonte, marca, mid))
    db.commit()
    print(db.execute("select fonte_imagem, tipo, count(*) from midia group by 1,2 order by 3 desc").fetchall())
    print(db.execute("select camera, count(*) from midia where camera is not null group by 1 order by 2 desc limit 8").fetchall())


if __name__ == "__main__":
    main()
