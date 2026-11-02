# Local AI photo gallery (case study)

English · [Português](README.pt-BR.md)

**Archived (2026-11).** Case study finished on 2026-10-28. The online gallery never existed; what remains is the
analysis pipeline and a local review screen.

## What it was

A personal photo collection (a Google Takeout with 7,100 files, 16.3 GB, 6,284 unique) classified entirely on this
machine, on the GPU, with nothing sent out: who appears, where, in which moment, which is the best shot of a
burst, what is probably junk (screenshot, meme, document, blurry photo) and a 0 to 10 score. A local screen
(Flask) showed the suggestions for review. It only recorded decisions; nothing was deleted.

## Pipeline

```
inventario.py  date and GPS (Takeout JSON > EXIF > file name), sha256 and phash
copias.py      copies sha256 misses (Google recompresses)
analise.py     GPU: CLIP ViT-L/14 (scene and embedding), LAION aesthetic score, sharpness, InsightFace faces
camera.py      origin: camera, screenshot, downloaded or scanned (EXIF)
notas.py       no GPU, re-runnable: people, moments, bursts, score, junk, suggested destination
tela.py        review at http://127.0.0.1:8765 (shortcut limpeza.cmd)
```

`processar.py` runs the pipeline over whatever came in. The other scripts in `src/` are inspection tools (contact
sheets, people, timeline, recognition diagnosis).

## What was learned

- **CLIP as a zero-shot classifier.** With text labels ("screenshot", "landscape", "document"), CLIP ViT-L/14
  separates scene and type well enough to make suggestions. The LAION aesthetic score, computed on the same
  embedding, comes for free.
- **The aesthetic score misleads.** Wallpapers and anime score high. Only camera photos (by EXIF or file name) can
  become highlights.
- **A simple rule beats the model on edge cases.** A photo with 2 or more faces is never junk; a document (ID card,
  driver's licence) gets its own destination, not junk.
- **InsightFace (buffalo_l) for faces.** A 512-dimension embedding per face, filtered by confidence (0.65) and minimum
  size.
- **Face grouping: hierarchical with average linkage, not DBSCAN.** DBSCAN chained different people together (A looks
  like B, who looks like C). `AgglomerativeClustering` with cosine distance, average linkage and a 0.7 threshold kept
  people apart. Names are attached per face and survive re-running the grouping.
- **Keep GPU work apart from rules.** The heavy analysis runs once and stores raw signals; scores and destinations are
  recomputed in seconds as often as needed. Calibration became cheap.
- **The moment is the unit, not the person.** Photos close in time and place form a moment; places and landscapes
  count as much as faces.

## Stack

Python 3.12, PyTorch with CUDA (RTX 3050 Ti, 4 GB), open_clip, onnxruntime, InsightFace, OpenCV, scikit-learn,
reverse_geocoder, SQLite, Flask.

## Data

No photo, face, embedding or database goes into git. The collection, the database (`galeria.db`) and the models live
in a folder outside the repository, and `.gitignore` blocks images, video, `.db` and model weights just in case. A
personal page built from the same collection is not part of the study and stays out of git.

## Architecture

[docs/arquitetura/](docs/arquitetura/README.md): use cases, process and containers.

## License

All rights reserved.
