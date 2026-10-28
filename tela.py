"""Tela de limpeza: servidor local da revisão (só nesta máquina).

  python tela.py   →  http://127.0.0.1:8765

Nada é apagado aqui. A tela só grava decisões na tabela `decisoes`;
quem move ou apaga arquivo é outra etapa, depois, com confirmação.
"""
import json
import sqlite3
import time
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file
from PIL import Image

from imagens import BANCO, CACHE, carregar

app = Flask(__name__, static_folder=None)
PASTA_TELA = Path(__file__).parent / "tela"
DECISOES = {"manter", "destaque", "lixo", "documento", "baixada"}
TRIAGEM = {"lixo", "baixada", "documento"}  # abas de grade única
POR_PAGINA = {"triagem": 120, "repetidas": 30, "momentos": 120}  # momentos: em fotos


def db() -> sqlite3.Connection:
    con = sqlite3.connect(BANCO)
    con.row_factory = sqlite3.Row
    return con


def item(r: sqlite3.Row) -> dict:
    return {k: r[k] for k in r.keys()}


# ── imagens ──────────────────────────────────────────────────────────

def em_cache(nome: str, gerar) -> Path:
    alvo = CACHE / nome
    if not alvo.exists():
        alvo.parent.mkdir(parents=True, exist_ok=True)
        img = gerar()
        if img is None:
            abort(404)
        img.save(alvo, "WEBP", quality=82)
    return alvo


def midia(mid: int) -> sqlite3.Row:
    r = db().execute("select caminho, tipo from midia where id=?", (mid,)).fetchone()
    if not r:
        abort(404)
    return r


@app.get("/mini/<int:mid>")
def mini(mid: int):
    def gerar():
        r = midia(mid)
        arr = carregar(r["caminho"], r["tipo"], 400)
        return Image.fromarray(arr) if arr is not None else None
    return send_file(em_cache(f"mini/{mid}.webp", gerar), "image/webp", max_age=86400)


@app.get("/grande/<int:mid>")
def grande(mid: int):
    r = midia(mid)
    if r["tipo"] == "video":
        return send_file(r["caminho"], conditional=True)

    def gerar():
        arr = carregar(r["caminho"], r["tipo"], 1800)
        return Image.fromarray(arr) if arr is not None else None
    return send_file(em_cache(f"grande/{mid}.webp", gerar), "image/webp", max_age=86400)


@app.get("/rosto/<int:rid>")
def rosto(rid: int):
    def gerar():
        f = db().execute("""select r.x1, r.y1, r.x2, r.y2, m.caminho, m.tipo
                            from rostos r join midia m on m.id = r.midia_id where r.id=?""", (rid,)).fetchone()
        if not f:
            return None
        arr = carregar(f["caminho"], f["tipo"])
        if arr is None:
            return None
        img = Image.fromarray(arr)
        w, h = img.size
        m = 0.3 * (f["x2"] - f["x1"])
        caixa = (max(0, (f["x1"] - m) * w), max(0, (f["y1"] - m) * h),
                 min(w, (f["x2"] + m) * w), min(h, (f["y2"] + m) * h))
        return img.crop(caixa).resize((200, 200))
    return send_file(em_cache(f"rosto/{rid}.webp", gerar), "image/webp", max_age=86400)


# ── dados ────────────────────────────────────────────────────────────

BASE = """
    from classificacao c join midia m on m.id = c.midia_id
    left join decisoes d on d.midia_id = c.midia_id
"""


@app.get("/api/resumo")
def resumo():
    con = db()
    pend = dict(con.execute(f"select c.destino, count(*) {BASE} where d.decisao is null group by 1").fetchall())
    rajadas = con.execute(f"""select count(distinct c.rajada) {BASE}
                              where c.rajada is not null and d.decisao is null""").fetchone()[0]
    momentos = con.execute(f"""select count(distinct c.momento_id) {BASE}
                               where c.destino in ('galeria','destaque') and d.decisao is null""").fetchone()[0]
    feitas = con.execute("select count(*) from decisoes").fetchone()[0]
    total = con.execute("select count(*) from classificacao").fetchone()[0]
    sem_nome = con.execute("select count(*) from pessoas where nome is null and n >= 8").fetchone()[0]
    return jsonify(lixo=pend.get("lixo", 0), baixada=pend.get("baixada", 0),
                   documento=pend.get("documento", 0), repetidas=rajadas, momentos=momentos,
                   pessoas=sem_nome, feitas=feitas, total=total)


@app.get("/api/triagem/<destino>")
def triagem(destino: str):
    if destino not in TRIAGEM:
        abort(404)
    rows = db().execute(f"""
        select c.midia_id id, m.tipo, c.lixo motivo, c.nota, m.data {BASE}
        where c.destino = ? and d.decisao is null
        order by case c.lixo when 'print' then 0 when 'foto de tela' then 1 else 2 end, m.data desc
        limit ?""", (destino, POR_PAGINA["triagem"])).fetchall()
    return jsonify([item(r) for r in rows])


@app.get("/api/repetidas")
def repetidas():
    con = db()
    grupos = [r[0] for r in con.execute(f"""
        select c.rajada {BASE} where c.rajada is not null and d.decisao is null
        group by c.rajada order by min(m.data) desc limit ?""", (POR_PAGINA["repetidas"],))]
    saida = []
    for g in grupos:
        rows = con.execute(f"""
            select c.midia_id id, m.tipo, c.nota, c.melhor_da_rajada melhor, c.destino {BASE}
            where c.rajada = ? order by m.data""", (g,)).fetchall()
        saida.append({"rajada": g, "itens": [item(r) for r in rows]})
    return jsonify(saida)


@app.get("/api/momentos")
def momentos():
    con = db()
    ids, fotos = [], 0  # página fecha em ~120 fotos, não em nº de momentos
    for mid, n in con.execute(f"""
            select c.momento_id, count(*) {BASE} where c.destino in ('galeria','destaque') and d.decisao is null
            group by c.momento_id order by c.momento_id = 0, min(m.data) desc"""):
        if ids and fotos + n > POR_PAGINA["momentos"]:
            break
        ids.append(mid)
        fotos += n
    nomes = {p["id"]: p["nome"] for p in con.execute("select id, nome from pessoas")}
    saida = []
    for mid in ids:
        mo = con.execute("select * from momentos where id=?", (mid,)).fetchone()
        rows = con.execute(f"""
            select c.midia_id id, m.tipo, c.nota, c.destino, c.tema {BASE}
            where c.momento_id = ? and c.destino in ('galeria','destaque') and d.decisao is null
            order by m.data""", (mid,)).fetchall()
        pessoas = [nomes.get(p) for p in json.loads(mo["pessoas"] or "[]")]
        saida.append({**item(mo), "pessoas": [p for p in pessoas if p and not p.startswith("__")],
                      "itens": [item(r) for r in rows]})
    return jsonify(saida)


@app.get("/api/destaques")
def destaques():
    rows = db().execute(f"""
        select c.midia_id id, m.tipo, c.nota, c.tema, coalesce(d.decisao, c.destino) efetivo {BASE}
        where c.tema is not null and m.tipo = 'foto' and m.fonte_imagem in ('camera','digitalizada')
          and coalesce(d.decisao, c.destino) not in ('lixo','documento','baixada')
          and (c.destino = 'destaque' or d.decisao = 'destaque' or c.nota >= 8.5)
        order by c.tema, c.nota desc""").fetchall()
    temas = {}
    for r in rows:
        temas.setdefault(r["tema"], []).append(item(r))
    return jsonify(temas)


@app.get("/api/pessoas")
def pessoas():
    con = db()
    rows = con.execute("select id, n, capa_rosto, nome from pessoas where n >= 4 order by n desc").fetchall()
    saida = []
    for p in rows:
        amostra = [r[0] for r in con.execute("""
            select min(id) from rostos where pessoa=? group by midia_id order by random() limit 6""", (p["id"],))]
        saida.append({**item(p), "amostra": amostra})
    return jsonify(saida)


# ── decisões ─────────────────────────────────────────────────────────

@app.post("/api/decidir")
def decidir():
    itens = request.get_json()["itens"]  # {midia_id: decisao}
    agora = int(time.time())
    con = db()
    for mid, dec in itens.items():
        if dec not in DECISOES:
            abort(400)
        con.execute("insert or replace into decisoes values (?,?,?)", (int(mid), dec, agora))
    con.commit()
    return jsonify(ok=len(itens))


@app.post("/api/desfazer")
def desfazer():
    ids = [int(i) for i in request.get_json()["ids"]]
    con = db()
    con.executemany("delete from decisoes where midia_id=?", [(i,) for i in ids])
    con.commit()
    return jsonify(ok=len(ids))


@app.post("/api/pessoa")
def nomear():
    corpo = request.get_json()
    pid, nome = int(corpo["id"]), (corpo.get("nome") or "").strip()
    con = db()
    rostos = [r[0] for r in con.execute("select id from rostos where pessoa=?", (pid,))]
    if nome:
        con.executemany("insert or replace into rosto_nome values (?,?)", [(r, nome) for r in rostos])
    else:
        con.executemany("delete from rosto_nome where rosto_id=?", [(r,) for r in rostos])
    con.execute("update pessoas set nome=? where id=?", (nome or None, pid))
    con.commit()
    return jsonify(ok=len(rostos))


@app.get("/")
def inicio():
    return send_file(PASTA_TELA / "index.html")


if __name__ == "__main__":
    app.run("127.0.0.1", 8765, threaded=True)
