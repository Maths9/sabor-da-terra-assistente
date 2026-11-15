"""Divisão dos documentos em trechos (chunks) por seção, com metadados para filtro e citação."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SEPARADOR = re.compile(r"^\s*([=_\-*])\1{9,}\s*$")
_ROTULO = re.compile(r"^(?P<rot>[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý0-9 /().,ºª&\-]{2,70}):(?P<resto>.*)$")
_PRODUTOR = re.compile(r"\bP\d{3}\b")
# Rótulos em maiúsculas que NÃO iniciam uma seção (campos soltos, como assinaturas).
_IGNORAR_ROTULOS = {"CPF", "CNPJ", "CEP", "RG", "TEL", "CARGO", "TITULAR", "SUPLENTE", "CRN-6", "CRMV-PE", "CREA-PE"}

TIPOS_LEGIVEIS = {
    "certificacao_organica": "Certificado de conformidade orgânica",
    "laudo_sanitario": "Laudo sanitário",
    "inspecao": "Relatório de inspeção (ADAGRO)",
    "contrato": "Contrato",
    "ficha_tecnica": "Ficha técnica de produto",
}


@dataclass
class Chunk:
    id: str
    texto: str  # texto exibido/citado (já mascarado)
    texto_indexado: str  # texto + cabeçalho de contexto, usado para gerar o embedding
    metadata: dict = field(default_factory=dict)


def classificar(caminho_rel: str) -> str:
    nome = caminho_rel.replace("\\", "/").lower()
    base = nome.rsplit("/", 1)[-1]
    if base.startswith("cert_organica"):
        return "certificacao_organica"
    if base.startswith("laudo_sanitario"):
        return "laudo_sanitario"
    if base.startswith("inspecao"):
        return "inspecao"
    if base.startswith("contrato"):
        return "contrato"
    return "ficha_tecnica"


def titulo_documento(texto: str) -> str:
    """Primeiras linhas de título (até a primeira linha em branco depois do título)."""
    linhas: list[str] = []
    for linha in texto.splitlines():
        if _SEPARADOR.match(linha):
            continue
        if not linha.strip():
            if linhas:
                break
            continue
        linhas.append(linha.strip())
        if len(linhas) == 3:
            break
    return " — ".join(linhas) if linhas else "(sem título)"


def _data_int(dia: str, mes: str, ano: str) -> int:
    return int(f"{ano}{mes}{dia}")


def extrair_validade(tipo: str, texto: str) -> tuple[int, str]:
    """Devolve (validade_ate como AAAAMMDD, tipo da validade). 0 = sem validade definida."""
    if tipo == "certificacao_organica":
        m = re.search(r"Data de Validade:\s*(\d{2})/(\d{2})/(\d{4})", texto)
        if m:
            return _data_int(*m.groups()), "certificado"
    if tipo == "contrato":
        m = re.search(r"VIG[ÊE]NCIA:\s*\d{2}/\d{2}/\d{4}\s*a\s*(\d{2})/(\d{2})/(\d{4})", texto, re.I)
        if m:
            return _data_int(*m.groups()), "contrato"
    return 0, ""


def metadados_documento(caminho_rel: str, texto: str) -> dict:
    tipo = classificar(caminho_rel)
    base = caminho_rel.replace("\\", "/").rsplit("/", 1)[-1]
    m = re.search(r"_(P\d{3})\.txt$", base)
    produtor_id = m.group(1) if m else ""
    validade_ate, validade_tipo = extrair_validade(tipo, texto)
    return {
        "arquivo": caminho_rel.replace("\\", "/"),
        "tipo": tipo,
        "titulo": titulo_documento(texto),
        "produtor_id": produtor_id,
        "validade_ate": validade_ate,
        "validade_tipo": validade_tipo,
    }


def dividir_em_secoes(texto: str) -> list[tuple[str, str]]:
    """Divide em seções a cada linha de rótulo em MAIÚSCULAS terminada em dois-pontos."""
    secoes: list[tuple[str, str]] = []
    titulo, buffer = "CABEÇALHO", []

    def fechar():
        corpo = "\n".join(buffer).strip()
        if corpo:
            secoes.append((titulo, corpo))

    for linha in texto.splitlines():
        if _SEPARADOR.match(linha):
            continue
        m = _ROTULO.match(linha)
        if m and m.group("rot").strip() not in _IGNORAR_ROTULOS:
            fechar()
            titulo, buffer = m.group("rot").strip(), [linha]
        else:
            buffer.append(linha)
    fechar()
    return secoes


def _quebrar(corpo: str, max_chars: int) -> list[str]:
    if len(corpo) <= max_chars:
        return [corpo]
    pedacos: list[str] = []
    for bloco in re.split(r"\n\s*\n", corpo):
        unidades = [bloco] if len(bloco) <= max_chars else bloco.splitlines()
        atual = ""
        for u in unidades:
            if atual and len(atual) + 1 + len(u) > max_chars:
                pedacos.append(atual)
                atual = u
            else:
                atual = f"{atual}\n{u}" if atual else u
        if atual:
            pedacos.append(atual)
    return pedacos


def criar_chunks(caminho_rel: str, texto: str, max_chars: int = 1400, min_chars: int = 250) -> list[Chunk]:
    meta_doc = metadados_documento(caminho_rel, texto)
    pacotes: list[tuple[list[str], str]] = []
    titulos: list[str] = []
    atual = ""
    for titulo, corpo in dividir_em_secoes(texto):
        for i, parte in enumerate(_quebrar(corpo, max_chars)):
            if atual and len(atual) + 2 + len(parte) > max_chars and len(atual) >= min_chars:
                pacotes.append((titulos, atual))
                titulos, atual = [], ""
            atual = f"{atual}\n\n{parte}" if atual else parte
            titulos.append(titulo if i == 0 else f"{titulo} (cont.)")
    if atual:
        if pacotes and len(atual) < min_chars // 2 and len(pacotes[-1][1]) + len(atual) <= int(max_chars * 1.3):
            t_ant, txt_ant = pacotes.pop()
            pacotes.append((t_ant + titulos, f"{txt_ant}\n\n{atual}"))
        else:
            pacotes.append((titulos, atual))

    slug = meta_doc["arquivo"].replace("/", "__")
    chunks: list[Chunk] = []
    for idx, (tits, txt) in enumerate(pacotes):
        unicos = list(dict.fromkeys(tits))
        secao = " + ".join(unicos)[:120]
        if meta_doc["produtor_id"]:
            produtores = {meta_doc["produtor_id"]}
        else:
            produtores = set(_PRODUTOR.findall(txt))
        meta = dict(meta_doc)
        meta.update(
            secao=secao,
            chunk_idx=idx,
            produtores="|" + "|".join(sorted(produtores)) + "|" if produtores else "",
        )
        cabecalho = (
            f"Documento: {meta['titulo']} | Tipo: {TIPOS_LEGIVEIS.get(meta['tipo'], meta['tipo'])}"
            + (f" | Produtor: {meta['produtor_id']}" if meta["produtor_id"] else "")
            + f"\nSeção: {secao}\n\n"
        )
        chunks.append(Chunk(id=f"{slug}::{idx:03d}", texto=txt, texto_indexado=cabecalho + txt, metadata=meta))
    return chunks
