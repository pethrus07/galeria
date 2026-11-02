"""Caminhos e leitura de imagem compartilhados (sem dependência de IA)."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
Image.MAX_IMAGE_PIXELS = None

RAIZ = Path.home() / "Fotos-Projeto"
BANCO = RAIZ / "galeria.db"
MODELOS = RAIZ / "modelos"
CACHE = RAIZ / "cache"


def carregar(caminho: str, tipo: str, lado: int = 1600) -> np.ndarray | None:
    """Imagem RGB com lado maior <= `lado` px (vídeo: quadro a 1/3 da duração)."""
    try:
        if tipo == "video":
            cap = cv2.VideoCapture(caminho)
            n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(n / 3)))
            ok, quadro = cap.read()
            cap.release()
            if not ok:
                return None
            img = Image.fromarray(cv2.cvtColor(quadro, cv2.COLOR_BGR2RGB))
        else:
            img = Image.open(caminho)
            img.draft("RGB", (lado, lado))
            img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((lado, lado))
        return np.asarray(img)
    except Exception:
        return None
