import { useEffect, useState } from "react";
import { produtoresFallback } from "../data/mockData";
import { fetchAuthConfig, fetchProdutores, loginPerfil } from "../services/agentService";
import type { ProdutorListaItem } from "../types";

interface ProducerLoginProps {
  initialProdutorId?: string | null;
  notice?: string | null;
  onEnter: (produtorId: string) => void;
  onBack: () => void;
}

// Seleção demonstrativa de produtor usando a lista real da cooperativa (/api/produtores) e token assinado.
export default function ProducerLogin({ initialProdutorId, notice, onEnter, onBack }: ProducerLoginProps) {
  const [produtores, setProdutores] = useState<ProdutorListaItem[]>(produtoresFallback);
  const [selectedId, setSelectedId] = useState<string>(initialProdutorId || produtoresFallback[0].id);
  const [codigo, setCodigo] = useState("");
  const [requerCodigo, setRequerCodigo] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [entrando, setEntrando] = useState(false);
  const [erroApi, setErroApi] = useState<string | null>(null);
  const [erroAuth, setErroAuth] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    Promise.all([fetchProdutores(), fetchAuthConfig()])
      .then(([lista, cfg]) => {
        if (!ativo) return;
        setRequerCodigo(Boolean(cfg.requer_codigo));
        if (lista.length > 0) {
          setProdutores(lista);
          setSelectedId((atual) =>
            lista.some((p) => p.id === atual) ? atual : lista[0].id
          );
        }
        setErroApi(null);
      })
      .catch((err) => {
        if (!ativo) return;
        setErroApi(err instanceof Error ? err.message : "API indisponível no momento.");
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });
    return () => {
      ativo = false;
    };
  }, []);

  const selecionado = produtores.find((p) => p.id === selectedId);

  async function entrar() {
    if (!selectedId || entrando) return;
    setEntrando(true);
    setErroAuth(null);
    try {
      await loginPerfil("produtor", selectedId, requerCodigo ? codigo : undefined);
      onEnter(selectedId);
    } catch (err) {
      setErroAuth(err instanceof Error ? err.message : "Falha ao autenticar produtor.");
    } finally {
      setEntrando(false);
    }
  }

  return (
    <main className="center">
      <div className="card login">
        <h2>Área do produtor</h2>
        <p className="muted">
          {requerCodigo
            ? "Selecione o produtor e informe o código de acesso."
            : "Selecione o produtor cadastrado na cooperativa (acesso demonstrativo protegido por token de sessão)."}
        </p>
        <label htmlFor="produtor-select">
          <small>Produtor</small>
        </label>
        <select
          id="produtor-select"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          disabled={carregando && produtores.length === 0}
        >
          {produtores.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id} — {p.nome} ({p.municipio})
            </option>
          ))}
        </select>
        {selecionado && (
          <small>
            Produtos: {selecionado.produtos.join(", ") || "—"} · Status: {selecionado.status}
          </small>
        )}
        {requerCodigo && (
          <>
            <label htmlFor="produtor-codigo">
              <small>Código de acesso</small>
            </label>
            <input
              id="produtor-codigo"
              type="password"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              placeholder="Digite o código do produtor"
            />
          </>
        )}
        {notice && <p className="aviso atencao">{notice}</p>}
        {erroApi && (
          <p className="aviso atencao">
            Não foi possível atualizar a lista ({erroApi}). Exibindo produtor padrão.
          </p>
        )}
        {erroAuth && <p className="aviso atencao">{erroAuth}</p>}
        <button
          className="btn wide"
          onClick={entrar}
          disabled={!selectedId || entrando || (requerCodigo && !codigo.trim())}
        >
          {entrando ? "Entrando…" : "Entrar como produtor"}
        </button>
        <button className="btn-ghost wide" onClick={onBack}>
          Voltar ao início
        </button>
      </div>
    </main>
  );
}
