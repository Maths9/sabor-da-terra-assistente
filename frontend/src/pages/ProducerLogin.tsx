import { useEffect, useState } from "react";
import { produtoresFallback } from "../data/mockData";
import { fetchProdutores } from "../services/agentService";
import type { ProdutorListaItem } from "../types";

interface ProducerLoginProps {
  initialProdutorId?: string | null;
  onEnter: (produtorId: string) => void;
  onBack: () => void;
}

// Seleção demonstrativa de produtor usando a lista real da cooperativa (/api/produtores).
export default function ProducerLogin({ initialProdutorId, onEnter, onBack }: ProducerLoginProps) {
  const [produtores, setProdutores] = useState<ProdutorListaItem[]>(produtoresFallback);
  const [selectedId, setSelectedId] = useState<string>(initialProdutorId || produtoresFallback[0].id);
  const [carregando, setCarregando] = useState(true);
  const [erroApi, setErroApi] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    fetchProdutores()
      .then((lista) => {
        if (!ativo || lista.length === 0) return;
        setProdutores(lista);
        setSelectedId((atual) =>
          lista.some((p) => p.id === atual) ? atual : lista[0].id
        );
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

  return (
    <main className="center">
      <div className="card login">
        <h2>Área do produtor</h2>
        <p className="muted">
          Selecione o produtor cadastrado na cooperativa (acesso demonstrativo, sem senha real).
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
        {erroApi && (
          <p className="aviso atencao">
            Não foi possível atualizar a lista ({erroApi}). Exibindo produtor padrão.
          </p>
        )}
        <button className="btn wide" onClick={() => onEnter(selectedId)} disabled={!selectedId}>
          Entrar como produtor
        </button>
        <button className="btn-ghost wide" onClick={onBack}>
          Voltar à área do cooperado
        </button>
      </div>
    </main>
  );
}
