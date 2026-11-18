import type { PedidoPendenteResumo, SessionContextState } from "../../types";

interface PedidosPanelProps {
  pedidos: PedidoPendenteResumo[];
  carregando: boolean;
  erro: string | null;
  sessionState: SessionContextState | null;
  onAtualizar: () => void;
  onSelecionarPedido: (pedido: PedidoPendenteResumo) => void;
}

function formatarDataHora(iso: string): string {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatarBrl(valor: number | null | undefined): string | null {
  if (typeof valor !== "number" || Number.isNaN(valor)) return null;
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function PedidosPanel({
  pedidos,
  carregando,
  erro,
  sessionState,
  onAtualizar,
  onSelecionarPedido,
}: PedidosPanelProps) {
  const temContexto = Boolean(
    sessionState?.produtorEmFoco || sessionState?.ultimoPedido || sessionState?.resultadoTriagem
  );
  const valorTriagem = formatarBrl(
    sessionState?.resultadoTriagem?.valor_total_estimado ??
      sessionState?.ultimoPedido?.valor_total_estimado
  );
  const compradorCtx =
    sessionState?.resultadoTriagem?.remetente_identificado ||
    sessionState?.ultimoPedido?.comprador ||
    null;
  const statusCtx =
    sessionState?.resultadoTriagem?.status_viabilidade ||
    sessionState?.ultimoPedido?.status_viabilidade ||
    null;
  const pendentesCtx =
    sessionState?.resultadoTriagem?.campos_pendentes ||
    sessionState?.ultimoPedido?.campos_pendentes ||
    [];

  return (
    <aside className="panel">
      {temContexto && (
        <div className="card">
          <h4>Contexto da Sessão ADK</h4>
          {sessionState?.produtorEmFoco && (
            <p className="row">
              <span>Produtor em foco</span>
              <span className="tag">{sessionState.produtorEmFoco}</span>
            </p>
          )}
          {compradorCtx && (
            <p className="row">
              <span>Último pedido</span>
              <span>{compradorCtx}</span>
            </p>
          )}
          {statusCtx && (
            <p className="row">
              <span>Viabilidade</span>
              <span className="tag">{statusCtx}</span>
            </p>
          )}
          {valorTriagem && (
            <p className="row">
              <span>Total estimado</span>
              <strong>{valorTriagem}</strong>
            </p>
          )}
          {pendentesCtx.length > 0 && (
            <small>Campos pendentes: {pendentesCtx.join(", ")}</small>
          )}
        </div>
      )}

      <div className="card">
        <div className="panel-card-head">
          <h4>Caixa de Pedidos ({pedidos.length})</h4>
          <button
            type="button"
            className="btn-ghost panel-mini-btn"
            onClick={onAtualizar}
            disabled={carregando}
          >
            {carregando ? "Atualizando…" : "Atualizar"}
          </button>
        </div>

        {erro && <p className="aviso atencao">{erro}</p>}

        {carregando && pedidos.length === 0 ? (
          <small>Carregando pedidos pendentes…</small>
        ) : pedidos.length === 0 ? (
          <small>Nenhum pedido pendente encontrado.</small>
        ) : (
          <div className="pedidos-list">
            {pedidos.map((p) => (
              <button
                key={p.id}
                type="button"
                className="pedido-item"
                onClick={() => onSelecionarPedido(p)}
                title={`Analisar ${p.id} no chat`}
              >
                <div className="pedido-top">
                  <strong>{p.id}</strong>
                  <span className="tag">{p.canal}</span>
                </div>
                <span className="pedido-comprador">{p.comprador}</span>
                <small>
                  {formatarDataHora(p.data_recebimento)} · {p.status}
                </small>
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
