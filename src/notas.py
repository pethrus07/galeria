"""Etapa 3 · notas e classificação (sem GPU, pode rodar quantas vezes quiser).

A partir de `sinais` e `rostos` calcula:
  - pessoas: agrupa os rostos (ligação média, cosseno); nome é dado depois na revisão
  - momentos: fotos próximas no tempo (e no espaço, quando há GPS)
  - rajadas: fotos quase iguais dentro do momento; aponta a melhor
  - nota 0–10 relativa ao acervo (estética + nitidez do rosto ou da cena)
  - lixo provável (print, meme, documento, tela, borrada) com motivo
  - destino sugerido e tema de destaque do Instagram
Sobrescreve as tabelas `classificacao`, `momentos` e `pessoas`; nomes de
pessoas e decisões do Pedro ficam em tabelas próprias e não são tocados.
"""
import json
import math
import sqlite3
from collections import Counter, defaultdict

import numpy as np
import reverse_geocoder as rg
from sklearn.cluster import AgglomerativeClustering

from imagens import BANCO

LIXO_CENAS = {"print", "meme", "documento"}
TEMAS = {  # cena -> destaque do Instagram
    "paisagem": "Natureza", "por_do_sol": "Natureza", "praia": "Praia",
    "cidade": "Rolês", "viagem": "Viagens", "festa": "Rolês", "bebida": "Rolês",
    "comida": "Comida", "pet": "Pets", "casal": "Nós", "grupo": "Amigos",
    "selfie": "Eu", "retrato": "Eu", "igreja": "Fé", "trabalho": "Trabalho",
}
GAP_MOMENTO = 3 * 3600
RAJADA_COS = 0.93
RAJADA_SEG = 120

ESQUEMA = """
drop table if exists classificacao;
create table classificacao (
    midia_id integer primary key,
    nota real, nota_estetica real, nota_tecnica real,
    lixo text,                 -- motivo, ou null
    momento_id integer,
    rajada integer,            -- id do grupo de quase iguais (null = sozinha)
    melhor_da_rajada integer,
    destino text,              -- galeria | destaque | repetida | lixo
    tema text,
    pessoas text               -- json [ids]
);
drop table if exists momentos;
create table momentos (
    id integer primary key, inicio integer, fim integer, n integer,
    cidade text, cena text, capa integer, nota real, pessoas text
);
drop table if exists pessoas;
create table pessoas (id integer primary key, n integer, capa_rosto integer, nome text);
drop table if exists nomes_pessoas;
-- nome dado na tela, por rosto: sobrevive a reagrupamentos (voto da maioria)
create table if not exists rosto_nome (rosto_id integer primary key, nome text);
create table if not exists decisoes (midia_id integer primary key, decisao text, quando integer);
"""
FOTO_REAL = {"camera", "digitalizada"}
SEM_DATA = 0  # id do momento das fotos sem data
IGNORAR = "__ignorar"


def percentil(v: np.ndarray) -> np.ndarray:
    ordem = v.argsort().argsort()
    return ordem / max(1, len(v) - 1)


def km(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = (math.sin((la2 - la1) * p / 2) ** 2 +
         math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))


def main() -> None:
    db = sqlite3.connect(BANCO)
    db.executescript(ESQUEMA)
    linhas = db.execute("""
        select m.id, m.data, m.lat, m.lon, m.largura, m.altura, m.tipo, m.pasta_celular,
               s.estetica, s.nitidez, s.brilho, s.cenas, s.cena1, s.n_rostos, s.clip, m.fonte_imagem,
               m.data_fonte
        from sinais s join midia m on m.id = s.midia_id where m.copia_de is null
        order by m.data""").fetchall()
    ids = [l[0] for l in linhas]
    pos = {mid: i for i, mid in enumerate(ids)}
    cenas = [json.loads(l[11]) for l in linhas]
    clip = np.stack([np.frombuffer(l[14], dtype=np.float16).astype(np.float32) for l in linhas])

    # ── lixo provável ──────────────────────────────────────────────
    # Foto com 2+ rostos é gente reunida: nunca lixo. Imagem que não veio da
    # câmera (internet, WhatsApp) não é lixo nem memória: destino "baixada".
    lixo = [None] * len(linhas)
    for i, l in enumerate(linhas):
        c, fonte, n_rostos = cenas[i], l[15], l[13]
        p_lixo = sum(c.get(k, 0) for k in LIXO_CENAS)
        tela = c.get("print", 0) + c.get("meme", 0) > 0.5 and n_rostos == 0
        if fonte == "print":
            lixo[i] = "print"
        elif fonte not in FOTO_REAL or n_rostos >= 2:
            continue
        elif c.get("documento", 0) > 0.5 and n_rostos == 0:
            lixo[i] = "documento"
        elif fonte == "camera" and tela:
            lixo[i] = "foto de tela"
        elif l[4] and l[5] and max(l[4], l[5]) < 500:
            lixo[i] = "miniatura"
        elif l[10] is not None and (l[10] < 18 or l[10] > 245):
            lixo[i] = "escura demais" if l[10] < 18 else "estourada"

    # ── rostos → pessoas ───────────────────────────────────────────
    rostos = db.execute("select id, midia_id, conf, area, nitidez, emb from rostos").fetchall()
    validos = [r for r in rostos if r[1] in pos and lixo[pos[r[1]]] is None
               and r[2] >= 0.65 and r[3] >= 0.002]
    db.execute("update rostos set pessoa = null")
    rosto_pessoa = {}
    nomeados = dict(db.execute("select rosto_id, nome from rosto_nome"))
    por_nome = {}  # nome -> pessoa canônica: grupos com o mesmo nome viram uma pessoa só
    if validos:
        E = np.stack([np.frombuffer(r[5], dtype=np.float32) for r in validos])
        # ligação média não encadeia rostos parecidos como o DBSCAN fazia
        rot = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                      distance_threshold=0.7).fit_predict(E)
        grupos = defaultdict(list)
        for r, g in zip(validos, rot):
            grupos[g].append(r)
        ordem = sorted((g for g in grupos.values() if len(g) >= 4), key=len, reverse=True)
        for pid, membros in enumerate(ordem, 1):
            capa = max(membros, key=lambda r: r[3] * (r[4] or 0))
            votos = Counter(nomeados[m[0]] for m in membros if m[0] in nomeados)
            nome = votos.most_common(1)[0][0] if votos else None
            db.execute("insert into pessoas values (?,?,?,?)", (pid, 0, capa[0], nome))
            if nome == IGNORAR:
                continue
            dono = por_nome.setdefault(nome, pid) if nome else pid
            for m in membros:
                rosto_pessoa[m[0]] = dono
    # rosto nomeado à mão fora de qualquer grupo entra na pessoa com aquele nome
    for rid, nome in nomeados.items():
        if rid not in rosto_pessoa and nome in por_nome:
            rosto_pessoa[rid] = por_nome[nome]
    db.executemany("update rostos set pessoa=? where id=?", [(p, r) for r, p in rosto_pessoa.items()])
    midia_do_rosto = {r[0]: r[1] for r in rostos}
    fotos_da_pessoa = defaultdict(set)
    for rid, p in rosto_pessoa.items():
        fotos_da_pessoa[p].add(midia_do_rosto[rid])
    # grupo juntado a outro fica com n = 0 e some da tela
    db.executemany("update pessoas set n=? where id=?",
                   [(len(fotos_da_pessoa.get(p, ())), p) for (p,) in db.execute("select id from pessoas").fetchall()])
    pessoas_da = defaultdict(set)
    nit_rosto = defaultdict(float)
    for r in rostos:
        if r[0] in rosto_pessoa:
            pessoas_da[r[1]].add(rosto_pessoa[r[0]])
        if r[2] >= 0.65 and r[4] is not None:
            nit_rosto[r[1]] = max(nit_rosto[r[1]], r[4])

    # ── notas relativas ao acervo ──────────────────────────────────
    est = np.array([l[8] for l in linhas])
    nit = np.array([nit_rosto.get(l[0]) or l[9] for l in linhas])
    p_est, p_nit = percentil(est), percentil(nit)
    nota = 10 * (0.65 * p_est + 0.35 * p_nit)
    nota = np.where([x is not None for x in lixo], np.minimum(nota, 3), nota)

    # ── momentos ───────────────────────────────────────────────────
    # sem data real (só a data do arquivo, que é a da extração) → momento SEM_DATA
    momento = [0] * len(linhas)
    mid_atual, ultimo_t, ultimo_gps = 0, None, None
    for i, l in enumerate(linhas):
        if l[16] == "arquivo":
            momento[i] = SEM_DATA
            continue
        gps = (l[2], l[3]) if l[2] is not None else None
        novo = ultimo_t is None or l[1] - ultimo_t > GAP_MOMENTO
        if not novo and gps and ultimo_gps and km(gps, ultimo_gps) > 30:
            novo = True
        mid_atual += novo
        momento[i] = mid_atual
        ultimo_t = l[1]
        ultimo_gps = gps or ultimo_gps if not novo else gps

    # cidade pelo GPS (offline)
    com_gps = [i for i, l in enumerate(linhas) if l[2] is not None]
    cidade = {}
    if com_gps:
        res = rg.search([(linhas[i][2], linhas[i][3]) for i in com_gps], mode=1, verbose=False)
        for i, r in zip(com_gps, res):
            cidade[i] = f"{r['name']}, {r['admin1']}" if r["cc"] == "BR" else f"{r['name']}, {r['cc']}"

    # ── rajadas (quase iguais, em sequência) ───────────────────────
    rajada = [None] * len(linhas)
    rid = 0
    for i in range(1, len(linhas)):
        if (momento[i] == momento[i - 1] and linhas[i][1] - linhas[i - 1][1] <= RAJADA_SEG
                and float(clip[i] @ clip[i - 1]) >= RAJADA_COS):
            if rajada[i - 1] is None:
                rid += 1
                rajada[i - 1] = rid
            rajada[i] = rajada[i - 1]
    melhor = {}
    for i, r in enumerate(rajada):
        if r is not None and (r not in melhor or nota[i] > nota[melhor[r]]):
            melhor[r] = i

    # ── destino e tema ─────────────────────────────────────────────
    corte_destaque = np.percentile(nota[[x is None for x in lixo]], 90) if any(x is None for x in lixo) else 10
    por_momento = defaultdict(list)
    for i, l in enumerate(linhas):
        tema = TEMAS.get(l[12])
        if lixo[i] == "documento":
            destino = "documento"
        elif lixo[i]:
            destino = "lixo"
        elif rajada[i] is not None and melhor[rajada[i]] != i:
            destino = "repetida"
        elif l[15] not in FOTO_REAL:
            destino = "baixada"
        elif nota[i] >= corte_destaque and tema and l[6] == "foto":
            destino = "destaque"
        else:
            destino = "galeria"
        por_momento[momento[i]].append(i)
        db.execute("insert into classificacao values (?,?,?,?,?,?,?,?,?,?,?)",
                   (l[0], round(float(nota[i]), 1), round(10 * float(p_est[i]), 1),
                    round(10 * float(p_nit[i]), 1), lixo[i], momento[i], rajada[i],
                    int(rajada[i] is not None and melhor[rajada[i]] == i), destino, tema,
                    json.dumps(sorted(pessoas_da.get(l[0], [])))))

    for m, idx in por_momento.items():
        bons = [i for i in idx if not lixo[i]] or idx
        capa = max(bons, key=lambda i: nota[i])
        cids = Counter(cidade[i] for i in idx if i in cidade)
        cena = Counter(linhas[i][12] for i in bons).most_common(1)[0][0]
        pes = Counter(p for i in idx for p in pessoas_da.get(linhas[i][0], []))
        db.execute("insert into momentos values (?,?,?,?,?,?,?,?,?)",
                   (m, linhas[idx[0]][1], linhas[idx[-1]][1], len(idx),
                    cids.most_common(1)[0][0] if cids else None, cena, linhas[capa][0],
                    round(float(np.mean(sorted(nota[bons])[-3:])), 1),
                    json.dumps([p for p, _ in pes.most_common(5)])))
    db.commit()
    resumo(db)


def resumo(db: sqlite3.Connection) -> None:
    q = lambda s: db.execute(s).fetchall()
    print("destino:", q("select destino, count(*) from classificacao group by 1 order by 2 desc"))
    print("lixo por motivo:", q("select lixo, count(*) from classificacao where lixo is not null group by 1 order by 2 desc"))
    print("temas de destaque:", q("select tema, count(*) from classificacao where destino='destaque' group by 1 order by 2 desc"))
    print("momentos:", q("select count(*), sum(n>=5), sum(n>=20) from momentos")[0], "(total, com 5+, com 20+)")
    print("pessoas (top 10 por nº de fotos):", q("select id, n from pessoas order by n desc limit 10"))
    print("rajadas:", q("select count(distinct rajada) from classificacao where rajada is not null")[0][0])


if __name__ == "__main__":
    main()
