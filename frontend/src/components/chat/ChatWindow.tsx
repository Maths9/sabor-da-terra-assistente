import { useEffect, useRef, useState } from "react";
import type { ChatMessage, UserType } from "../../types";
import { clearConversation, getConversationHistory, sendMessage } from "../../services/agentService";
import { sugestoes } from "../../data/mockData";
import MessageBubble from "./MessageBubble";

interface ChatWindowProps {
  userType: UserType;
  produtorId?: string;
}

export default function ChatWindow({ userType, produtorId }: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    getConversationHistory(userType, produtorId)
  );
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages(getConversationHistory(userType, produtorId));
    setText("");
    setLoading(false);
  }, [userType, produtorId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function enviar(conteudo: string) {
    const msg = conteudo.trim();
    if (!msg || loading) return;
    setText("");
    setLoading(true);
    setMessages((m) => [
      ...m,
      { id: crypto.randomUUID(), role: "user", content: msg, timestamp: new Date().toISOString() },
    ]);
    const resposta = await sendMessage(msg, userType, produtorId);
    setMessages((m) => [...m, resposta]);
    setLoading(false);
  }

  function limpar() {
    clearConversation(userType, produtorId);
    setMessages(getConversationHistory(userType, produtorId));
  }

  const subtitulo =
    userType === "produtor" && produtorId
      ? `Portal do Produtor · ${produtorId}`
      : "Operador da Cooperativa · Sabor da Terra";

  return (
    <section className="chat">
      <header className="chat-header">
        <span className="avatar" aria-hidden>🌱</span>
        <div>
          <strong>Assistente Sabor da Terra</strong>
          <small>{subtitulo}</small>
        </div>
        <button className="btn-ghost" onClick={limpar}>Nova conversa</button>
      </header>
      <div className="chat-body">
        {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
        {loading && (
          <div className="msg msg-bot">
            <span className="avatar">🌱</span>
            <div className="bubble typing">Consultando assistente…</div>
          </div>
        )}
        {messages.length <= 1 && (
          <div className="chips">
            {sugestoes[userType].map((s) => (
              <button key={s} className="chip" onClick={() => enviar(s)}>{s}</button>
            ))}
          </div>
        )}
        <div ref={endRef} />
      </div>
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); enviar(text); }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Digite sua mensagem…"
          aria-label="Mensagem"
        />
        <button type="submit" className="btn" disabled={!text.trim() || loading} aria-label="Enviar">
          ➤
        </button>
      </form>
    </section>
  );
}
