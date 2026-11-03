# Galeria

[English](README.md) · Português

Galeria com IA local (estudo de caso).

## Status

Arquivado (novembro de 2026). Estudo de caso concluído em 28/10/2026. A galeria online nunca existiu; o que ficou
é a esteira de análise e uma tela local de revisão.

## O que faz

Um acervo pessoal de fotos (um Google Takeout com 7.100 arquivos, 16,3 GB, 6.284 únicos) classificado inteiro
nesta máquina, na GPU, sem mandar nada para fora: quem aparece, onde, em que momento, qual é a melhor de uma
rajada, o que é lixo provável (print, meme, documento, foto borrada) e uma nota de 0 a 10. Uma tela local
(Flask) mostrava as sugestões para revisão. Ela só gravava decisões; nada era apagado.

## Esteira

```
inventario.py  data e GPS (JSON do Takeout > EXIF > nome do arquivo), sha256 e phash
copias.py      cópias que o sha256 não pega (o Google recomprime)
analise.py     GPU: CLIP ViT-L/14 (cena e embedding), nota estética LAION, nitidez, rostos InsightFace
camera.py      de onde veio: câmera, print, baixada ou digitalizada (EXIF)
notas.py       sem GPU, re-rodável: pessoas, momentos, rajadas, nota, lixo, destino sugerido
tela.py        revisão em http://127.0.0.1:8765 (atalho limpeza.cmd)
```

`processar.py` roda a esteira sobre o que entrou novo. Os demais scripts em `src/` são ferramentas de
conferência (folhas de contato, pessoas, linha do tempo, diagnóstico de reconhecimento).

## O que ficou de aprendizado

- **CLIP como classificador sem treino.** Com rótulos em texto ("print de tela", "paisagem", "documento"), o
  CLIP ViT-L/14 separa cena e tipo bem o bastante para sugerir. A nota estética da LAION, calculada sobre o mesmo
  embedding, sai de graça.
- **A nota estética engana.** Papel de parede e anime ganham nota alta. Só foto de câmera (pelo EXIF ou pelo nome
  do arquivo) pode virar destaque.
- **Regra simples vence modelo em caso de borda.** Foto com 2 ou mais rostos nunca é lixo; documento (CNH, RG) tem
  destino próprio, não lixo.
- **InsightFace (buffalo_l) para rostos.** Embedding de 512 dimensões por rosto, filtrado por confiança (0,65) e
  tamanho mínimo.
- **Agrupar rostos: hierárquico com ligação média, não DBSCAN.** O DBSCAN encadeava pessoas diferentes (A parece
  B, que parece C). `AgglomerativeClustering` com distância de cosseno, ligação média e limiar 0,7 manteve as
  pessoas separadas. O nome é dado por rosto e sobrevive a re-rodar o agrupamento.
- **Separar GPU de regra.** A análise pesada roda uma vez e grava sinais brutos; notas e destinos são recalculados
  em segundos quantas vezes for preciso. Calibrar virou barato.
- **Momento é a unidade, não a pessoa.** Fotos próximas no tempo e no lugar formam um momento; lugar e paisagem
  contam tanto quanto rosto.

## Stack

Python 3.12, PyTorch com CUDA (RTX 3050 Ti, 4 GB), open_clip, onnxruntime, InsightFace, OpenCV, scikit-learn,
reverse_geocoder, SQLite, Flask.

## Arquitetura

[docs/arquitetura/](docs/arquitetura/README.md): casos de uso, processo e containers.

## Decisões e limites conhecidos

Nada de foto, rosto, embedding ou banco entra no git. O acervo, o banco (`galeria.db`) e os modelos ficam numa
pasta fora do repositório, e o `.gitignore` bloqueia imagem, vídeo, `.db` e pesos de modelo por garantia. Uma
página pessoal feita com o mesmo acervo não é parte do estudo e fica fora do git.

## Licença

MIT. Veja [LICENSE](LICENSE).
