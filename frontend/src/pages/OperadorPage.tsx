import { useCallback, useEffect, useRef, useState } from "react";
import ChatWindow from "../components/chat/ChatWindow";
import PedidosPanel from "../components/operator/PedidosPanel";
import { fetchPedidosPendentes } from "../services/agentService";
import type { PedidoPendenteResumo, SessionContextState } from "../types";

// Chat + Caixa de pedidos do Operador da Cooperativa (/api/pedidos-pendentes + /api/chat).
export default function OperadorPage() {
  const [aberto, setAberto] = useState(false);
  const [pedidos, setPedidos] = useState<PedidoPendenteResumo[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [sessionState, setSessionState] = useState<SessionContextState | null>(null);
  const [promptRequest, setPromptRequest] = useState<{ id: number; text: string } | null>(null);
  const promptSeqRef = useRef(0);

  const carregarPedidos = useCallback(() => {
    let ativo = true;
    setCarregando(true);
    setErro(null);
    fetchPedidosPendentes()
      .then((lista) => {
        if (ativo) setPedidos(lista);
      })
      .catch((err) => {
        if (ativo) {
          setErro(err instanceof Error ? err.message : "Erro ao carregar caixa de pedidos.");
        }
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });
    return () => {
      ativo = false;
    };
  }, []);

  useEffect(() => carregarPedidos(), [carregarPedidos]);

  function analisarPedido(pedido: PedidoPendenteResumo) {
    promptSeqRef.current += 1;
    setPromptRequest({
      id: promptSeqRef.current,
      text: `Consulte os detalhes do pedido ${pedido.id} (${pedido.comprador}) e faça a triagem completa com verificação de compliance.`,
    });
    setAberto(false);
  }

  return (
    <main className="page-producer">
      <button className="btn-ghost toggle-panel" onClick={() => setAberto(!aberto)}>
        {aberto ? "Ocultar caixa de pedidos" : `Ver caixa de pedidos (${pedidos.length})`}
      </button>
      <div className={`panel-wrap ${aberto ? "open" : ""}`}>
        <PedidosPanel
          pedidos={pedidos}
          carregando={carregando}
          erro={erro}
          sessionState={sessionState}
          onAtualizar={carregarPedidos}
          onSelecionarPedido={analisarPedido}
        />
      </div>
      <ChatWindow
        userType="operador"
        promptRequest={promptRequest}
        onSessionStateChange={setSessionState}
      />
    </main>
  );
}
