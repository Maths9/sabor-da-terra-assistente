import { useState } from "react";
import ChatWindow from "../components/chat/ChatWindow";
import InfoPanel from "../components/producer/InfoPanel";
import { produtorMock } from "../data/mockData";

// Chat + painel de informações. No celular o painel fica recolhível.
export default function ProducerPage() {
  const [aberto, setAberto] = useState(false);
  return (
    <main className="page-producer">
      <button className="btn-ghost toggle-panel" onClick={() => setAberto(!aberto)}>
        {aberto ? "Ocultar painel" : "Ver painel do produtor"}
      </button>
      <div className={`panel-wrap ${aberto ? "open" : ""}`}><InfoPanel p={produtorMock} /></div>
      <ChatWindow userType="produtor" />
    </main>
  );
}
