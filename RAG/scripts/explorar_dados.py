#!/usr/bin/env python3
"""
Exploração dos dados da Cooperativa Sabor da Terra (Integrante 3 - Dados & RAG).

Uso:  python explorar_dados.py <pasta_com_csvs_e_pedidos.json> [arquivo_de_saida.txt]

Não assume nomes de colunas: procura por palavras-chave. Tudo que imprimir com
[!] é ponto a revisar manualmente. Rode e cole a saída no relatório.
"""
import sys, re, json, unicodedata
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path
import pandas as pd

# Windows: forçar UTF-8 na saída e permitir gravar a saída num arquivo (2º argumento)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, texto):
        for st in self.streams:
            st.write(texto)

    def flush(self):
        for st in self.streams:
            st.flush()


_SAIDA = None
if len(sys.argv) > 2:
    _SAIDA = open(sys.argv[2], "w", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, _SAIDA)

pd.set_option("display.width", 200, "display.max_columns", 40, "display.max_colwidth", 60)
DATA = Path(sys.argv[1] if len(sys.argv) > 1 else ".")


def achar_pasta(base):
    """Se produtores.csv não está em `base`, procura nas subpastas."""
    if (base / "produtores.csv").exists():
        return base
    achados = sorted(base.rglob("produtores.csv"))
    return achados[0].parent if achados else base


DATA = achar_pasta(DATA)
print(f"Pasta analisada: {DATA.resolve()}")
if not list(DATA.glob("*.csv")):
    print("[!] Nenhum .csv encontrado nessa pasta nem nas subpastas.")
    print('    Passe a pasta que tem os CSVs, ex.: python explorar_dados.py "C:\\caminho\\da\\pasta"')
    sys.exit(1)
HOJE = pd.Timestamp(date.today())


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower().strip())


def ler(path):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"não consegui ler {path}")


def cols(df, *pats):
    return [c for c in df.columns if any(re.search(p, norm(c)) for p in pats)]


def datas(serie):
    """Datas ISO (AAAA-MM-DD) ou BR (DD/MM/AAAA). NÃO usar dayfirst em ISO: inverte dia/mês."""
    d = pd.to_datetime(serie, errors="coerce", format="ISO8601")
    falhas = d.isna() & serie.notna()
    if falhas.any():
        d[falhas] = pd.to_datetime(serie[falhas], errors="coerce", dayfirst=True)
    return d


def titulo(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


# ---------------------------------------------------------------- 1. inventário
esperados = ["produtores", "financeiro", "sazonalidade", "tabela_precos_outubro_2026", "lotes"]
tabelas = {}
for nome in esperados:
    p = DATA / f"{nome}.csv"
    if p.exists():
        tabelas[nome] = ler(p)
    else:
        print(f"[!] FALTANDO: {p.name}")
for p in sorted(DATA.glob("*.csv")):
    if p.stem not in tabelas:
        tabelas[p.stem] = ler(p)

for nome, df in tabelas.items():
    titulo(f"TABELA {nome}: {df.shape[0]} linhas x {df.shape[1]} colunas")
    print(df.dtypes.to_string())
    nulos = df.isna().sum()
    nulos = nulos[nulos > 0]
    print("\nNulos:", nulos.to_dict() if len(nulos) else "nenhum")
    vazios = {c: int((df[c].astype(str).str.strip() == "").sum()) for c in df.columns}
    vazios = {c: n for c, n in vazios.items() if n}
    if vazios:
        print("[!] Strings vazias:", vazios)
    print("Linhas duplicadas (exatas):", int(df.duplicated().sum()))
    for c in cols(df, r"^id", r"_id$", r"codigo", r"^lote"):
        d = df[c].duplicated(keep=False) & df[c].notna()
        if d.any():
            print(f"[!] Valores repetidos em '{c}':", df.loc[d, c].unique()[:10].tolist())
    print(df.head(3).to_string())

# ---------------------------------------------------------------- 2. chaves entre tabelas
titulo("CHAVES ENTRE TABELAS (colunas com mesmo nome)")
for (a, da), (b, db) in combinations(tabelas.items(), 2):
    for c in set(da.columns) & set(db.columns):
        if not cols(da[[c]], r"id", r"produtor", r"codigo", r"lote", r"produto"):
            continue
        so_a = set(da[c].dropna().astype(str)) - set(db[c].dropna().astype(str))
        so_b = set(db[c].dropna().astype(str)) - set(da[c].dropna().astype(str))
        if so_a or so_b:
            print(f"[!] '{c}': só em {a}: {sorted(so_a)[:8]} | só em {b}: {sorted(so_b)[:8]}")
        else:
            print(f"OK  '{c}' bate entre {a} e {b}")

# ---------------------------------------------------------------- 3. armadilhas
titulo("ARMADILHA: lote 2024-089")
achou = False
for nome, df in tabelas.items():
    m = df.astype(str).apply(lambda s: s.str.contains("2024-089", regex=False)).any(axis=1)
    if m.any():
        achou = True
        print(f"Encontrado em {nome}:\n", df[m].to_string())
if not achou:
    print("[!] '2024-089' NÃO existe em nenhuma tabela. Conferir pedidos.json e documentos.")

titulo("ARMADILHA: certificações (produtores.csv) vencidas / a vencer em 60 dias")
if "produtores" in tabelas:
    pr = tabelas["produtores"]
    for c in cols(pr, r"valid", r"venc"):
        d = datas(pr[c])
        venc = pr[d < HOJE]
        breve = pr[(d >= HOJE) & (d <= HOJE + timedelta(days=60))]
        print(f"Coluna {c}: vencidas={len(venc)} a vencer<=60d={len(breve)}")
        if len(venc): print(venc.to_string())
        if len(breve): print(breve.to_string())
    print("\nObs.: documentos já indicam P008 vencida (30/09/2026) e P004 vence 01/12/2026.")

titulo("ARMADILHA: pendências financeiras")
if "financeiro" in tabelas:
    fi = tabelas["financeiro"]
    for c in cols(fi, r"status", r"situacao"):
        print(fi[c].value_counts(dropna=False).to_string())
        pend = fi[fi[c].astype(str).map(norm).str.contains("pend|atras|vencid|aberto")]
        print(f"[!] {len(pend)} transações pendentes/atrasadas")
        pc = cols(fi, r"produtor")
        vc = cols(fi, r"valor_total", r"total") or cols(fi, r"valor")
        if pc and vc:
            print(pend.groupby(pc[0])[vc[0]].agg(["count", "sum"]).sort_values("sum", ascending=False).to_string())

titulo("ARMADILHA: dados bancários / PII e contas repetidas")
for nome, df in tabelas.items():
    pii = cols(df, r"banco", r"agencia", r"conta", r"pix", r"cpf", r"cnpj")
    if pii:
        print(f"[!] {nome}: colunas sensíveis {pii} (mascarar antes de indexar/expor)")
        for c in cols(df, r"conta", r"pix"):
            d = df[c].duplicated(keep=False) & df[c].notna()
            if d.any():
                print(f"[!] valor repetido em '{c}':\n", df.loc[d].to_string())

titulo("ARMADILHA: nomes de produto diferentes")
nomes = {}
for nome, df in tabelas.items():
    for c in [c for c in cols(df, r"produto", r"item") if not re.search(r"produtor", norm(c))]:
        for v in df[c].dropna().astype(str).unique():
            nomes.setdefault(norm(v), set()).add(f"{nome}:{v}")
for k in sorted(nomes):
    print(f"  {k:35s} <- {sorted(nomes[k])}")
print("Compare com os nomes dos contratos/fichas (ex.: 'Goiaba paluma', 'Queijo coalho', 'Mel silvestre').")

titulo("ARMADILHA: preço da tabela x contrato PNAE")
PNAE = {"banana prata": 3.80, "goiaba": 5.20, "manga": 5.50, "maracuja": 6.00, "macaxeira": 3.50,
        "inhame": 5.00, "batata doce": 4.00, "alface": 2.80, "coentro": 2.00, "tomate": 7.00,
        "queijo coalho": 34.00, "mel silvestre": 58.00, "ovos": 18.00, "frango": 29.00}
if "tabela_precos_outubro_2026" in tabelas:
    tp = tabelas["tabela_precos_outubro_2026"]
    txt = tp.astype(str).apply(lambda s: s.map(norm))
    for item, preco in PNAE.items():
        m = txt.apply(lambda s: s.str.contains(item, regex=False)).any(axis=1)
        print(f"\n[contrato PNAE {item}: R$ {preco:.2f}]")
        print(tp[m].to_string() if m.any() else "  [!] sem linha na tabela de preços")

titulo("SAZONALIDADE: produtos com 'nenhuma' em nov/dez (contratos ativos)")
if "sazonalidade" in tabelas:
    sz = tabelas["sazonalidade"]
    m = sz.astype(str).apply(lambda s: s.map(norm).eq("nenhuma"))
    print(sz[m.any(axis=1)].to_string())

titulo("LOTES: lotes de P008 depois de 30/09/2026 (orgânico?)")
if "lotes" in tabelas:
    lo = tabelas["lotes"]
    pc, dc = cols(lo, r"produtor_id", r"produtor"), cols(lo, r"entrega") or cols(lo, r"data")
    if pc and dc:
        d = datas(lo[dc[0]])
        m = lo[pc[0]].astype(str).str.contains("P008") & (d > "2026-09-30")
        print(lo[m].to_string() if m.any() else "nenhum lote de P008 após 30/09")

# ---------------------------------------------------------------- 4. pedidos.json
titulo("pedidos.json")
pj = DATA / "pedidos.json"
if pj.exists():
    ped = json.loads(pj.read_text(encoding="utf-8"))
    ped = ped if isinstance(ped, list) else ped.get("pedidos", ped)
    dfp = pd.json_normalize(ped)
    print(dfp.shape, "\nColunas:", dfp.columns.tolist())
    print("Nulos:", dfp.isna().sum()[dfp.isna().sum() > 0].to_dict())
    for c in cols(dfp, r"tipo", r"categoria"):
        print(dfp[c].value_counts().to_string())
else:
    print("[!] pedidos.json não encontrado")


# ---------------------------------------------------------------- 5. checagens específicas do projeto
titulo("CHECAGENS ESPECÍFICAS (usam os nomes de colunas reais)")
try:
    pr, fi, lo = tabelas["produtores"], tabelas["financeiro"], tabelas["lotes"]
    pj_ped = json.loads((DATA / "pedidos.json").read_text(encoding="utf-8"))

    print("\n[1] Vendas DEPOIS do vencimento da certificação orgânica do produtor")
    m = fi.merge(pr[["id", "certificacao_organica", "validade_certificacao"]], left_on="produtor_id", right_on="id")
    m["venc"] = datas(m["validade_certificacao"])
    m["dt"] = datas(m["data"])
    print(m[m["dt"] > m["venc"]][["id_transacao", "produtor_id", "data", "produto", "valor_unitario", "venc"]].to_string())

    print("\n[2] Produtores com flag 'sim' mas validade vencida/<=60d (a flag sozinha engana)")
    pr["venc"] = datas(pr["validade_certificacao"])
    print(pr[(pr["certificacao_organica"] == "sim") & (pr["venc"] <= HOJE + timedelta(days=60))][["id", "nome_completo", "validade_certificacao"]].to_string())

    print("\n[3] Pendentes vencidos em", HOJE.date())
    pe = fi[fi["status_pagamento"] == "pendente"].copy()
    pe["atraso"] = (HOJE - datas(pe["data_vencimento"])).dt.days
    print(pe[pe["atraso"] > 0][["id_transacao", "produtor_id", "comprador", "valor_total", "atraso"]].to_string())
    print("Total pendente: R$", pe["valor_total"].sum(), "| vencido: R$", pe[pe["atraso"] > 0]["valor_total"].sum())

    print("\n[4] Vendas (financeiro) sem lote correspondente = buraco de rastreabilidade")
    chave = lambda d: d.apply(lambda r: (r["produtor_id"], r["produto"], int(r["quantidade_kg"]), r["comprador"]), axis=1)
    sem = fi[~chave(fi).isin(set(chave(lo)))]
    print(sem[["id_transacao", "produtor_id", "produto", "quantidade_kg", "comprador"]].to_string())

    print("\n[5] Folhosas transportadas acima de 5 C (ficha: 2-5 C)")
    t = pd.to_numeric(lo["temperatura_transporte_c"], errors="coerce")
    fol = lo["produto"].isin(["alface", "rucula", "rúcula", "couve", "coentro", "espinafre", "cebolinha", "hortelã", "manjericão"])
    print(lo[fol & (t > 5)][["lote_id", "produto", "temperatura_transporte_c"]].to_string())

    print("\n[6] Preço pago x tabela (convencional/orgânico) — divergências")
    tp = tabelas["tabela_precos_outubro_2026"].copy()
    tp["conv"] = pd.to_numeric(tp["preco_convencional"], errors="coerce")
    tp["org"] = pd.to_numeric(tp["preco_organico"], errors="coerce")
    for _, r in fi.iterrows():
        cand = tp[tp["produto"].map(norm).str.startswith(norm(r["produto"]).split()[0] + (" " + norm(r["produto"]).split()[1] if len(norm(r["produto"]).split()) > 1 and norm(r["produto"]).split()[0] in ("queijo", "mel", "goiaba", "manga", "farinha", "doce", "geleia", "frango", "ovos", "manteiga") else ""))]
        if cand.empty:
            continue
        faixa = set(cand["conv"].dropna()) | set(cand["org"].dropna())
        if r["valor_unitario"] not in faixa:
            print(f"  {r['id_transacao']} {r['produtor_id']} {r['produto']}: pago {r['valor_unitario']} | tabela conv={sorted(cand['conv'].dropna())} org={sorted(cand['org'].dropna())}")

    print("\n[7] IDs de pedido: pedidos.json x lotes (precisam ser a mesma chave)")
    ids_ped = {p["id"] for p in pj_ped}
    print("pedidos.json:", sorted(ids_ped)[:3], "... | lotes:", sorted(lo["pedido_id"].unique())[:3], "... | em comum:", ids_ped & set(lo["pedido_id"]))

    print("\n[8] CPFs com dígito verificador válido (dados simulados costumam falhar)")
    def cpf_ok(c):
        d = re.sub(r"\D", "", str(c))
        if len(d) != 11 or len(set(d)) == 1:
            return False
        for n in (9, 10):
            if (sum(int(d[i]) * (n + 1 - i) for i in range(n)) * 10 % 11) % 10 != int(d[n]):
                return False
        return True
    print(int(pr["cpf"].map(cpf_ok).sum()), "de", len(pr))
except Exception as e:  # não derruba o resto da análise
    print("[!] checagens específicas puladas (faltam tabelas ou colunas):", repr(e))

if _SAIDA:
    _SAIDA.close()
    sys.stdout = sys.__stdout__
    print(f"\nSaída gravada em: {sys.argv[2]}")
