"""Limpeza e padronização das tabelas operacionais -> data/clean/.

Uso (na raiz do projeto):  py -m sabor.limpeza

Os arquivos de data/raw NUNCA são alterados. As versões limpas:
  * não têm CPF, PIX, banco, agência, conta, telefone, e-mail, endereço nem data de nascimento;
  * trazem nomes de produto padronizados e a unidade real (un, maço, dúzia, kg);
  * trazem a tabela de restrições por produtor (SIE, DAP/CAF) com a fonte de cada informação.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

from . import config

PII_PRODUTORES = ["cpf", "data_nascimento", "telefone", "email", "endereco", "chave_pix", "banco", "agencia", "conta_corrente"]
PII_MOVIMENTO = ["produtor_cpf", "chave_pix_deposito"]


def chave(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"\s+", " ", t)


# nome encontrado nos dados/documentos (sem acento, minúsculo) -> nome canônico
SINONIMOS = {
    "goiaba": "goiaba paluma",
    "goiaba vermelha": "goiaba paluma",
    "goiaba paluma in natura": "goiaba paluma",
    "mandioca": "macaxeira",
    "aipim": "macaxeira",
    "manga": "manga tommy",
    "manga tommy atkins": "manga tommy",
    "tommy atkins": "manga tommy",
    "queijo de coalho": "queijo coalho",
    "queijo coalho artesanal": "queijo coalho",
    "mel jandaira": "mel de jandaíra",
    "mel de abelha jandaira": "mel de jandaíra",
    "ovos": "ovos caipira",
    "frango": "frango caipira",
}
# produto da tabela de preços -> (produto base, grade)
GRADES = {
    "goiaba paluma extra": ("goiaba paluma", "extra"),
    "goiaba paluma especial": ("goiaba paluma", "especial"),
    "tomate santa cruz": ("tomate", "santa cruz"),
    "tomate cereja": ("tomate", "cereja"),
    "pimentão verde": ("pimentão", "verde"),
    "pimentão colorido": ("pimentão", "colorido"),
}

# Situação de registro sanitário (SIE) e restrições, com a fonte de cada afirmação.
RESTRICOES_MANUAIS = {
    "P002": dict(sie_situacao="vigente", sie_registro="PE-SIE-0892", fonte="inspecao_adagro_2026.txt; cert_organica P002"),
    "P003": dict(sie_situacao="vigente", sie_registro="PE-SIE-0756", fonte="inspecao_adagro_2026.txt; laudo_sanitario P003"),
    "P007": dict(sie_situacao="informado", sie_registro="PE-SIE-1203", fonte="cert_organica P007; ficha queijo_coalho"),
    "P008": dict(
        sie_situacao="pendente",
        venda_restrita="mel sem SIE: não pode abastecer canais que exigem registro (ex.: PNAE)",
        fonte="ficha mel_silvestre",
    ),
    "P018": dict(
        sie_situacao="pendente",
        venda_restrita="mel sem SIE: não pode abastecer canais que exigem registro (ex.: PNAE)",
        fonte="ficha mel_silvestre",
    ),
    "P011": dict(
        sie_situacao="nao_possui",
        venda_restrita="venda limitada a consumidor final (sem SIE)",
        fonte="ficha queijo_coalho",
    ),
    "P017": dict(
        sie_situacao="nao_possui",
        venda_restrita="frango: intermediação suspensa (ADAGRO NC-001, grave); ovos só em venda direta ao consumidor final",
        fonte="inspecao_adagro_2026.txt",
    ),
    "P005": dict(dap_caf="VIGENTE (confirmado pela ADAGRO)", fonte="inspecao_adagro_2026.txt"),
}


def canonico(nome: str) -> str:
    return SINONIMOS.get(chave(nome), str(nome).strip().lower())


def _ler(pasta: Path, nome: str) -> pd.DataFrame:
    return pd.read_csv(Path(pasta) / nome, dtype=str)


def _num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def _restricoes(docs: Path, ids: list[str]) -> pd.DataFrame:
    dap: dict[str, str] = {}
    for arq in sorted(Path(docs).rglob("cert_organica_*_P*.txt")):
        m = re.search(r"_(P\d{3})\.txt$", arq.name)
        d = re.search(r"DAP/CAF:\s*(\S+)", arq.read_text(encoding="utf-8"))
        if m and d:
            dap[m.group(1)] = d.group(1)
    linhas = []
    for pid in ids:
        base = dict(produtor_id=pid, sie_situacao="desconhecido", sie_registro="", dap_caf="desconhecido", venda_restrita="", fonte="")
        if pid in dap:
            base.update(dap_caf=dap[pid], fonte=f"cert_organica {pid}")
        extra = RESTRICOES_MANUAIS.get(pid, {})
        fontes = [f.strip() for texto in (base["fonte"], extra.get("fonte", "")) for f in texto.split(";") if f.strip()]
        base.update({k: v for k, v in extra.items() if k != "fonte"})
        base["fonte"] = "; ".join(dict.fromkeys(fontes))
        linhas.append(base)
    return pd.DataFrame(linhas)


def limpar(raw: Path = config.DATA_RAW, docs: Path = config.DATA_DOCS, saida: Path = config.DATA_CLEAN) -> dict:
    raw, saida = Path(raw), Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    relatorio: dict = {"tabelas": {}, "colunas_pessoais_removidas": {}, "avisos": []}

    # ---- tabela de preços (base para unidades)
    tp = _ler(raw, "tabela_precos_outubro_2026.csv")
    tp["preco_convencional"] = _num(tp["preco_convencional"])
    tp["preco_organico"] = _num(tp["preco_organico"])
    tp["desconto_atacado_pct"] = _num(tp["desconto_atacado_pct"]).astype("Int64")
    tp["volume_minimo_atacado_kg"] = _num(tp["volume_minimo_atacado_kg"]).astype("Int64")
    tp["produto"] = tp["produto"].str.strip().str.lower()
    tp["produto_base"] = tp["produto"].map(lambda p: GRADES.get(p, (canonico(p), ""))[0])
    tp["grade"] = tp["produto"].map(lambda p: GRADES.get(p, ("", ""))[1])
    obs = tp["observacao"].fillna("")
    tp["produtor_ref"] = obs.str.extract(r"(P\d{3})")[0].fillna("")
    tp["venda_direta_apenas"] = obs.str.lower().str.contains("venda direta")
    unidade_por_base = tp.drop_duplicates("produto_base").set_index("produto_base")["unidade"].to_dict()

    # ---- dimensão de produto
    nomes = set(tp["produto_base"])
    for arq, col in (("financeiro.csv", "produto"), ("lotes.csv", "produto"), ("sazonalidade.csv", "produto")):
        nomes |= {canonico(p) for p in _ler(raw, arq)[col].dropna()}
    dim = pd.DataFrame(
        {
            "produto_canonico": sorted(nomes),
            "unidade_padrao": [unidade_por_base.get(n, "kg") for n in sorted(nomes)],
            "sinonimos": ["|".join(k for k, v in SINONIMOS.items() if v == n) for n in sorted(nomes)],
            "variantes": ["|".join(g for g, (b, _) in GRADES.items() if b == n) for n in sorted(nomes)],
        }
    )
    sem_unidade = [n for n in nomes if n not in unidade_por_base]
    if sem_unidade:
        relatorio["avisos"].append(f"Produtos sem unidade na tabela de preços (assumido kg): {sorted(sem_unidade)}")

    # ---- produtores (sem dados pessoais)
    pr = _ler(raw, "produtores.csv")
    pub = pd.DataFrame(
        {
            "id": pr["id"],
            "nome_completo": pr["nome_completo"],
            "municipio": pr["municipio"],
            "status": pr["status"],
            "produtos": pr["produtos"].map(lambda s: "|".join(canonico(p) for p in str(s).split(","))),
            "certificacao_organica_declarada": pr["certificacao_organica"],
            "validade_certificacao": pd.to_datetime(pr["validade_certificacao"], format="%Y-%m-%d", errors="coerce").dt.strftime("%Y-%m-%d"),
        }
    )
    prod_prod = pub[["id", "produtos"]].assign(produto=pub["produtos"].str.split("|")).explode("produto")
    prod_prod = prod_prod.rename(columns={"id": "produtor_id"})[["produtor_id", "produto"]]
    relatorio["colunas_pessoais_removidas"]["produtores"] = [c for c in PII_PRODUTORES if c in pr.columns]

    # ---- financeiro e lotes
    fin = _ler(raw, "financeiro.csv")
    fin["produto"] = fin["produto"].map(canonico)
    fin = fin.rename(columns={"quantidade_kg": "quantidade"})
    fin["quantidade"] = _num(fin["quantidade"])
    fin["valor_unitario"] = _num(fin["valor_unitario"])
    fin["valor_total"] = _num(fin["valor_total"])
    fin["unidade"] = fin["produto"].map(lambda p: unidade_por_base.get(p, "kg"))
    relatorio["colunas_pessoais_removidas"]["financeiro"] = [c for c in PII_MOVIMENTO if c in fin.columns]
    fin = fin.drop(columns=[c for c in PII_MOVIMENTO if c in fin.columns])

    lo = _ler(raw, "lotes.csv")
    lo["produto"] = lo["produto"].map(canonico)
    lo = lo.rename(columns={"quantidade_kg": "quantidade", "pedido_id": "pedido_id_lote"})
    lo["quantidade"] = _num(lo["quantidade"])
    lo["unidade"] = lo["produto"].map(lambda p: unidade_por_base.get(p, "kg"))
    lo["temperatura_c"] = _num(lo["temperatura_transporte_c"])
    lo["transporte"] = lo["temperatura_c"].map(lambda t: "ambiente" if pd.isna(t) else "refrigerado")
    relatorio["colunas_pessoais_removidas"]["lotes"] = [c for c in PII_MOVIMENTO if c in lo.columns]
    lo = lo.drop(columns=[c for c in PII_MOVIMENTO + ["temperatura_transporte_c"] if c in lo.columns])

    rest = _restricoes(docs, list(pub["id"])) if Path(docs).exists() else pd.DataFrame()

    saidas = {
        "produtores_publico": pub,
        "produtores_produtos": prod_prod,
        "financeiro_limpo": fin,
        "lotes_limpo": lo,
        "tabela_precos_limpa": tp,
        "dim_produto": dim,
        "restricoes_produtor": rest,
    }
    for nome, df in saidas.items():
        df.to_csv(saida / f"{nome}.csv", index=False, encoding="utf-8")
        relatorio["tabelas"][nome] = {"linhas": int(df.shape[0]), "colunas": list(df.columns)}
    relatorio["avisos"].append(
        "pedido_id_lote (lotes) NÃO é o mesmo identificador de pedidos.json (ex.: PED-2026-OCT-001 x PED-2026-001): não fazer join."
    )
    (saida / "relatorio_limpeza.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return relatorio


def main():
    ap = argparse.ArgumentParser(description="Gera as tabelas limpas em data/clean.")
    ap.add_argument("--raw", default=str(config.DATA_RAW))
    ap.add_argument("--docs", default=str(config.DATA_DOCS))
    ap.add_argument("--saida", default=str(config.DATA_CLEAN))
    a = ap.parse_args()
    rel = limpar(a.raw, a.docs, a.saida)
    for nome, info in rel["tabelas"].items():
        print(f"  {nome}.csv: {info['linhas']} linhas")
    for aviso in rel["avisos"]:
        print("  aviso:", aviso)
    print(f"Tabelas limpas gravadas em {a.saida}")


if __name__ == "__main__":
    main()
