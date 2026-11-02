"""Etapa 2 · análise com IA (local, na GPU).

Para cada mídia única (uma por sha256) grava sinais brutos:
  - CLIP ViT-L/14: embedding + probabilidade de cada cena/tipo
  - nota estética (LAION aesthetic predictor sobre o embedding do CLIP)
  - nitidez (variância do Laplaciano), brilho, contraste
  - rostos (InsightFace buffalo_l): caixa, confiança, embedding 512-d
Vídeo: analisa um quadro a 1/3 da duração.
Notas e destinos saem depois, em notas.py, sem rodar a GPU de novo.

  python analise.py --amostra 60   # calibração
  python analise.py                # tudo que falta
"""
import json
import sqlite3
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import torch
import open_clip
import onnxruntime as ort
from PIL import Image

from imagens import BANCO, MODELOS, carregar

URL_ESTETICA = ("https://github.com/christophschuhmann/improved-aesthetic-predictor/raw/main/"
                "sac+logos+ava1-l14-linearMSE.pth")

# rótulo interno -> descrição em inglês para o CLIP
CENAS = {
    "selfie": "a selfie taken with a phone",
    "retrato": "a portrait photo of a person",
    "casal": "a photo of a couple together",
    "grupo": "a group photo of friends or family",
    "paisagem": "a beautiful landscape photo of nature",
    "por_do_sol": "a photo of a sunset or the sky",
    "praia": "a photo of a beach or the sea",
    "cidade": "a photo of a city street or buildings",
    "viagem": "a travel photo at a tourist spot",
    "comida": "a photo of food or a meal",
    "bebida": "a photo of drinks at a bar",
    "pet": "a photo of a dog or a cat",
    "festa": "a photo at a party or a concert",
    "igreja": "a photo inside a church or a religious event",
    "casa": "a photo inside a house",
    "carro": "a photo of a car or motorcycle",
    "trabalho": "a photo of a computer, office or meeting",
    "documento": "a photo of a document, receipt or paper",
    "print": "a screenshot of a phone or computer screen",
    "meme": "a meme or an image with lots of text",
    "arte": "a drawing, illustration or graphic design",
    "objeto": "a product photo of an object",
}

ESQUEMA = """
create table if not exists sinais (
    midia_id integer primary key,
    estetica real, nitidez real, brilho real, contraste real,
    cenas text,             -- json {rotulo: prob}
    cena1 text, cena2 text,
    n_rostos integer, maior_rosto real,
    clip blob               -- float16[768], normalizado
);
create table if not exists rostos (
    id integer primary key,
    midia_id integer,
    x1 real, y1 real, x2 real, y2 real,   -- fração da imagem
    conf real, area real, nitidez real,
    emb blob,                             -- float32[512], normalizado
    pessoa integer                        -- preenchido no agrupamento
);
create index if not exists ix_rosto_midia on rostos(midia_id);
"""


class Estetica(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = torch.nn.Sequential(
            torch.nn.Linear(768, 1024), torch.nn.Dropout(0.2),
            torch.nn.Linear(1024, 128), torch.nn.Dropout(0.2),
            torch.nn.Linear(128, 64), torch.nn.Dropout(0.1),
            torch.nn.Linear(64, 16), torch.nn.Linear(16, 1))

    def forward(self, x):
        return self.layers(x)


def nitidez(cinza: np.ndarray) -> float:
    return float(np.log1p(cv2.Laplacian(cinza, cv2.CV_64F).var()))


def main() -> None:
    amostra = int(sys.argv[sys.argv.index("--amostra") + 1]) if "--amostra" in sys.argv else None
    MODELOS.mkdir(exist_ok=True)
    db = sqlite3.connect(BANCO)
    db.executescript(ESQUEMA)

    pendentes = db.execute("""
        select m.id, m.caminho, m.tipo from midia m
        where m.id in (select min(id) from midia where erro is null group by sha256)
          and m.copia_de is null
          and m.id not in (select midia_id from sinais)
        order by random()""").fetchall()
    if amostra:
        pendentes = pendentes[:amostra]
    print(f"{len(pendentes)} mídias para analisar", flush=True)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    clip, _, prep = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="openai", device=dev, precision="fp16" if dev == "cuda" else "fp32")
    clip.eval()
    tok = open_clip.get_tokenizer("ViT-L-14")
    with torch.no_grad():
        t = clip.encode_text(tok(list(CENAS.values())).to(dev))
        textos = torch.nn.functional.normalize(t.float(), dim=-1)

    arq_est = MODELOS / "estetica-l14.pth"
    if not arq_est.exists():
        urllib.request.urlretrieve(URL_ESTETICA, arq_est)
    est = Estetica()
    est.load_state_dict(torch.load(arq_est, map_location="cpu"))
    est.to(dev).eval()

    ort.preload_dlls()
    from insightface.app import FaceAnalysis
    faces = FaceAnalysis(name="buffalo_l", root=str(MODELOS), allowed_modules=["detection", "recognition"],
                         providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    faces.prepare(ctx_id=0, det_size=(640, 640))
    print("rostos rodando em:", faces.models["detection"].session.get_providers()[0], flush=True)

    rotulos = list(CENAS)
    with ThreadPoolExecutor(6) as pool:
        imgs = pool.map(lambda r: carregar(r[1], r[2]), pendentes)
        for i, ((mid, caminho, tipo), arr) in enumerate(zip(pendentes, imgs), 1):
            if arr is None:
                db.execute("update midia set erro='nao abriu na analise' where id=?", (mid,))
                continue
            h, w = arr.shape[:2]
            with torch.no_grad():
                x = prep(Image.fromarray(arr)).unsqueeze(0).to(dev)
                e = torch.nn.functional.normalize(clip.encode_image(x.half() if dev == "cuda" else x).float(), dim=-1)
                probs = (100 * e @ textos.T).softmax(-1)[0].cpu().numpy()
                nota_est = float(est(e)[0, 0])
            ordem = probs.argsort()[::-1]
            cenas = {rotulos[j]: round(float(probs[j]), 4) for j in ordem[:6]}

            cinza = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            achados = faces.get(arr[:, :, ::-1].copy())
            maior = 0.0
            for f in achados:
                x1, y1, x2, y2 = [float(v) for v in f.bbox]
                area = max(0, x2 - x1) * max(0, y2 - y1) / (w * h)
                maior = max(maior, area)
                recorte = cinza[max(0, int(y1)):int(y2), max(0, int(x1)):int(x2)]
                db.execute("insert into rostos (midia_id,x1,y1,x2,y2,conf,area,nitidez,emb) values (?,?,?,?,?,?,?,?,?)",
                           (mid, x1 / w, y1 / h, x2 / w, y2 / h, float(f.det_score), area,
                            nitidez(recorte) if recorte.size else None,
                            f.normed_embedding.astype(np.float32).tobytes()))
            db.execute("insert into sinais values (?,?,?,?,?,?,?,?,?,?,?)",
                       (mid, nota_est, nitidez(cinza), float(cinza.mean()), float(cinza.std()),
                        json.dumps(cenas), rotulos[ordem[0]], rotulos[ordem[1]],
                        len(achados), maior, e[0].cpu().numpy().astype(np.float16).tobytes()))
            if i % 200 == 0:
                db.commit()
                print(f"  {i}/{len(pendentes)}", flush=True)
    db.commit()
    print("pronto", flush=True)


if __name__ == "__main__":
    main()
