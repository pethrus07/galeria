"""Extrai os zips do Takeout para a pasta de entrada.

Zips do Google Fotos vão inteiros (mídia + JSON de metadados).
Zips do Drive: só fotos e vídeos, documentos ficam de fora.
"""
import sys
import zipfile
from pathlib import Path

MIDIA = {"jpg", "jpeg", "png", "heic", "heif", "webp", "gif", "dng", "mp4", "mov", "3gp", "mkv", "webm"}
DESTINO = Path.home() / "Fotos-Projeto" / "entrada" / "takeout"


def extrair(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        n = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            nome = info.filename
            partes = nome.split("/")
            if ".." in partes or nome.startswith("/"):
                continue
            ext = nome.rsplit(".", 1)[-1].lower() if "." in partes[-1] else ""
            eh_drive = len(partes) > 1 and partes[1] == "Drive"
            if eh_drive and ext not in MIDIA:
                continue
            alvo = DESTINO / Path(*partes)
            if alvo.exists() and alvo.stat().st_size == info.file_size:
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(alvo, "wb") as dst:
                while bloco := src.read(1 << 20):
                    dst.write(bloco)
            n += 1
        print(f"{zip_path.name}: {n} arquivos extraídos", flush=True)


if __name__ == "__main__":
    for z in sys.argv[1:]:
        extrair(Path(z))
