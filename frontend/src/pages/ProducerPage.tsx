import { useEffect, useState } from "react";
import ChatWindow from "../components/chat/ChatWindow";
import InfoPanel from "../components/producer/InfoPanel";
import { fetchPainelProdutor } from "../services/agentService";
import type { ProducerProfile } from "../types";

interface ProducerPageProps {
  produtorId: string;
  onTrocarProdutor: () => void;
}

// Chat + painel de informações carregados da API real (/api/produtores/{id}).
export default function ProducerPage({ produtorId, onTrocarProdutor }: ProducerPageProps) {
  const [aberto, setAberto] = useState(false);
  const [perfil, setPerfil] = useState<ProducerProfile | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let ativo = true;
    setCarregando(true);
    setErro(null);
    fetchPainelProdutor(produtorId)
      .then((dados) => {
        if (ativo) setPerfil(dados);
      })
      .catch((err) => {
        if (ativo) {
          setPerfil(null);
          setErro(err instanceof Error ? err.message : "Erro ao carregar painel do produtor.");
        }
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });
    return () => {
      ativo = false;
    };
  }, [produtorId]);

  return (
    <main className="page-producer">
      <button className="btn-ghost toggle-panel" onClick={() => setAberto(!aberto)}>
        {aberto ? "Ocultar painel" : "Ver painel do produtor"}
      </button>
      <div className={`panel-wrap ${aberto ? "open" : ""}`}>
        {carregando && (
          <aside className="panel">
            <div className="card">
              <strong>Carregando painel…</strong>
              <small>Buscando dados de {produtorId} na cooperativa.</small>
            </div>
          </aside>
        )}
        {!carregando && erro && (
          <aside className="panel">
            <div className="card">
              <strong>Painel indisponível</strong>
              <p className="aviso atencao">{erro}</p>
              <button type="button" className="btn-ghost wide" onClick={onTrocarProdutor}>
                Trocar produtor
              </button>
            </div>
          </aside>
        )}
        {!carregando && perfil && (
          <InfoPanel p={perfil} onTrocarProdutor={onTrocarProdutor} />
        )}
      </div>
      <ChatWindow userType="produtor" produtorId={produtorId} />
    </main>
  );
}
