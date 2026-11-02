"""Etapa 1 · inventário.

Varre ~/Fotos-Projeto/entrada, lê data/GPS (JSON do Takeout > EXIF > nome do
arquivo), calcula sha256 (cópia exata) e phash (quase igual) e grava tudo em
~/Fotos-Projeto/galeria.db. Só lê as fotos, nunca altera nem apaga.
"""
import hashlib
import json
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import cv2
import imagehash
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
Image.MAX_IMAGE_PIXELS = None

RAIZ = Path.home() / "Fotos-Projeto"
ENTRADA = RAIZ / "entrada"
BANCO = RAIZ / "galeria.db"

FOTO = {"jpg", "jpeg", "png", "heic", "heif", "webp", "gif", "dng"}
VIDEO = {"mp4", "mov", "3gp", "mkv", "webm"}

ESQUEMA = """
create table if not exists midia (
    id integer primary key,
    caminho text unique,
    origem text,          -- fotos | drive | celular | digitalizada
    album text,           -- pasta do Takeout ("Fotos de 2025", "Arquivar", nome de álbum)
    tipo text,            -- foto | video
    ext text,
    bytes integer,
    sha256 text,
    largura integer,
    altura integer,
    duracao real,
    data integer,         -- unix, quando a foto foi tirada
    data_fonte text,      -- takeout | exif | nome | arquivo
    lat real,
    lon real,
    pasta_celular text,   -- localFolderName do Takeout (WhatsApp, Screenshots…)
    arquivada integer,
    favorita integer,
    phash text,
    erro text
);
create index if not exists ix_sha on midia(sha256);
create index if not exists ix_data on midia(data);
"""

NOME_DATA = re.compile(r"(20\d{2}|19\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_ T]?(\d{2})?[-_.]?(\d{2})?[-_.]?(\d{2})?")


def origem_de(p: Path) -> tuple[str, str]:
    partes = p.relative_to(ENTRADA).parts
    if partes[0] in ("celular", "digitalizadas"):
        origem = "celular" if partes[0] == "celular" else "digitalizada"
        return origem, partes[1] if len(partes) > 2 else ""
    if len(partes) > 2 and partes[2] == "Drive":
        return "drive", partes[3] if len(partes) > 4 else ""
    return "fotos", partes[3] if len(partes) > 4 else ""


def json_takeout(p: Path) -> dict | None:
    """Acha o .supplemental-metadata.json da mídia (também a variante (1), (2)…)."""
    candidatos = [p.with_name(p.name + ".supplemental-metadata.json")]
    m = re.match(r"^(.*)\((\d+)\)(\.[^.]+)$", p.name)
    if m:
        base = m.group(1) + m.group(3)
        candidatos.append(p.with_name(f"{base}.supplemental-metadata({m.group(2)}).json"))
    editado = re.sub(r"-(editado|edited)(\.[^.]+)$", r"\2", p.name)
    if editado != p.name:
        candidatos.append(p.with_name(editado + ".supplemental-metadata.json"))
    for c in candidatos:
        if c.exists():
            return json.loads(c.read_text(encoding="utf-8"))
    # nomes longos vêm truncados no Takeout
    for c in p.parent.glob(p.name[:40] + "*.json"):
        dados = json.loads(c.read_text(encoding="utf-8"))
        if dados.get("title") == p.name:
            return dados
    return None


def exif_de(img: Image.Image) -> tuple[int | None, float | None, float | None]:
    ex = img.getexif()
    data = None
    bruto = ex.get_ifd(0x8769).get(0x9003) or ex.get(0x0132)
    if bruto:
        try:
            data = int(datetime.strptime(str(bruto)[:19], "%Y:%m:%d %H:%M:%S").timestamp())
        except ValueError:
            pass
    lat = lon = None
    gps = ex.get_ifd(0x8825)
    if gps and 2 in gps and 4 in gps:
        def graus(v):
            return float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
        try:
            lat = graus(gps[2]) * (-1 if gps.get(1) == "S" else 1)
            lon = graus(gps[4]) * (-1 if gps.get(3) == "W" else 1)
        except (TypeError, ZeroDivisionError, IndexError):
            lat = lon = None
    return data, lat, lon


def data_do_nome(nome: str) -> int | None:
    m = NOME_DATA.search(nome)
    if not m:
        return None
    try:
        v = [int(g) if g else 0 for g in m.groups()]
        return int(datetime(*v).timestamp())
    except ValueError:
        return None


def analisar(p: Path) -> dict:
    ext = p.suffix.lower().lstrip(".")
    origem, album = origem_de(p)
    r = {"caminho": str(p), "origem": origem, "album": album, "ext": ext,
         "tipo": "video" if ext in VIDEO else "foto", "bytes": p.stat().st_size,
         "data": None, "data_fonte": None, "lat": None, "lon": None,
         "largura": None, "altura": None, "duracao": None, "phash": None,
         "pasta_celular": None, "arquivada": 0, "favorita": 0, "erro": None}

    h = hashlib.sha256()
    with open(p, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    r["sha256"] = h.hexdigest()

    meta = json_takeout(p) if origem == "fotos" else None
    if meta:
        ts = (meta.get("photoTakenTime") or {}).get("timestamp")
        if ts:
            r["data"], r["data_fonte"] = int(ts), "takeout"
        geo = meta.get("geoData") or {}
        if geo.get("latitude") or geo.get("longitude"):
            r["lat"], r["lon"] = geo["latitude"], geo["longitude"]
        pasta = (((meta.get("googlePhotosOrigin") or {}).get("mobileUpload") or {})
                 .get("deviceFolder") or {}).get("localFolderName")
        r["pasta_celular"] = pasta or None
        r["arquivada"] = int(bool(meta.get("archived")))
        r["favorita"] = int(bool(meta.get("favorited")))

    try:
        if r["tipo"] == "foto":
            with Image.open(p) as img:
                d, lat, lon = exif_de(img)
                if r["data"] is None and d:
                    r["data"], r["data_fonte"] = d, "exif"
                if r["lat"] is None and lat:
                    r["lat"], r["lon"] = lat, lon
                img = ImageOps.exif_transpose(img)
                r["largura"], r["altura"] = img.size
                img.thumbnail((512, 512))
                r["phash"] = str(imagehash.phash(img.convert("RGB")))
        else:
            cap = cv2.VideoCapture(str(p))
            r["largura"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
            r["altura"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
            fps, n = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
            r["duracao"] = round(n / fps, 1) if fps else None
            cap.release()
    except Exception as e:  # foto corrompida não derruba o inventário
        r["erro"] = f"{type(e).__name__}: {e}"[:200]

    if r["data"] is None:
        d = data_do_nome(p.name)
        r["data"], r["data_fonte"] = (d, "nome") if d else (int(p.stat().st_mtime), "arquivo")
    return r


def main() -> None:
    db = sqlite3.connect(BANCO)
    db.executescript(ESQUEMA)
    feitos = {c for (c,) in db.execute("select caminho from midia")}
    arquivos = [p for p in ENTRADA.rglob("*")
                if p.is_file() and p.suffix.lower().lstrip(".") in FOTO | VIDEO and str(p) not in feitos]
    print(f"{len(arquivos)} arquivos novos para inventariar", flush=True)
    cols = None
    with ThreadPoolExecutor(8) as pool:
        for i, r in enumerate(pool.map(analisar, arquivos), 1):
            cols = cols or list(r)
            db.execute(f"insert into midia ({','.join(cols)}) values ({','.join('?' * len(cols))})",
                       [r[c] for c in cols])
            if i % 500 == 0:
                db.commit()
                print(f"  {i}/{len(arquivos)}", flush=True)
    db.commit()
    resumo(db)


def resumo(db: sqlite3.Connection) -> None:
    q = lambda s: db.execute(s).fetchall()
    total, gb = q("select count(*), sum(bytes)/1e9 from midia")[0]
    unicos, gb_unicos = q("select count(*), sum(b)/1e9 from (select max(bytes) b from midia group by sha256)")[0]
    print(f"\nTOTAL: {total} arquivos, {gb:.1f} GB  ·  únicos: {unicos} ({gb_unicos:.1f} GB)")
    for linha in q("select origem, tipo, count(*), round(sum(bytes)/1e9,2) from midia group by 1,2 order by 1,2"):
        print("  ", linha)
    print("por ano:", q("select strftime('%Y', data, 'unixepoch') a, count(*) from midia group by a order by a"))
    print("data veio de:", q("select data_fonte, count(*) from midia group by 1"))
    print("com GPS:", q("select count(*) from midia where lat is not null")[0][0])
    print("pasta no celular:", q("select coalesce(pasta_celular,'?'), count(*) from midia group by 1 order by 2 desc limit 12"))
    print("erros:", q("select count(*) from midia where erro is not null")[0][0])


if __name__ == "__main__":
    resumo(sqlite3.connect(BANCO)) if "--resumo" in sys.argv else main()
