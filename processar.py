"""Roda o pipeline inteiro sobre o que entrou novo em ~/Fotos-Projeto/entrada.

  python processar.py           # roda já
  python processar.py --vigiar  # espera chegar arquivo e parar de mudar por 90 s

inventário → cópias → análise (GPU) → origem da imagem → notas.
"""
import subprocess
import sys
import time
from pathlib import Path

from imagens import RAIZ

ENTRADA = RAIZ / "entrada"
AQUI = Path(__file__).parent
PASSOS = ["inventario.py", "copias.py", "analise.py", "camera.py", "notas.py"]


def retrato() -> tuple[int, int]:
    arquivos = [p for p in ENTRADA.rglob("*") if p.is_file()]
    return len(arquivos), sum(p.stat().st_size for p in arquivos)


def vigiar(quieto: int = 90, maximo: int = 3 * 3600) -> None:
    inicio, antes = time.time(), retrato()
    print(f"vigiando {ENTRADA} (agora: {antes[0]} arquivos)", flush=True)
    ultimo_mudou = None
    while time.time() - inicio < maximo:
        time.sleep(10)
        agora = retrato()
        if agora != antes:
            print(f"  chegando: {agora[0]} arquivos, {agora[1] / 1e9:.2f} GB", flush=True)
            antes, ultimo_mudou = agora, time.time()
        elif ultimo_mudou and time.time() - ultimo_mudou >= quieto:
            print("parou de chegar, processando", flush=True)
            return
    sys.exit("nada chegou no tempo limite")


def main() -> None:
    if "--vigiar" in sys.argv:
        vigiar()
    for passo in PASSOS:
        print(f"\n── {passo}", flush=True)
        r = subprocess.run([sys.executable, str(AQUI / passo)], cwd=AQUI)
        if r.returncode:
            sys.exit(f"{passo} falhou ({r.returncode})")


if __name__ == "__main__":
    main()
