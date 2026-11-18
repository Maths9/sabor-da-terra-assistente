import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, SessionContextState, UserType } from "../../types";
import {
  clearConversation,
  getConversationHistory,
  getSessionContextState,
  restoreConversation,
  sendMessage,
} from "../../services/agentService";
import { sugestoes } from "../../data/mockData";
import MessageBubble from "./MessageBubble";

interface ChatWindowProps {
  userType: UserType;
  produtorId?: string;
  promptRequest?: { id: number; text: string } | null;
  onSessionStateChange?: (state: SessionContextState | null) => void;
}

export default function ChatWindow({
  userType,
  produtorId,
  promptRequest,
  onSessionStateChange,
}: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    getConversationHistory(userType, produtorId)
  );
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [restaurando, setRestaurando] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);
  const convGenRef = useRef(0);
  const lastPromptIdRef = useRef<number | null>(null);

  useEffect(() => {
    let ativo = true;
    const gen = ++convGenRef.current;
    setMessages(getConversationHistory(userType, produtorId));
    onSessionStateChange?.(getSessionContextState(userType, produtorId));
    setText("");
    setLoading(false);
    setRestaurando(true);

    restoreConversation(userType, produtorId)
      .then((hist) => {
        if (ativo && convGenRef.current === gen) {
          setMessages(hist);
          onSessionStateChange?.(getSessionContextState(userType, produtorId));
        }
      })
      .finally(() => {
        if (ativo && convGenRef.current === gen) {
          setRestaurando(false);
        }
      });

    return () => {
      ativo = false;
    };
  }, [userType, produtorId, onSessionStateChange]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const enviar = useCallback(
    async (conteudo: string) => {
      const msg = conteudo.trim();
      if (!msg || loading || restaurando) return;
      const gen = convGenRef.current;
      setText("");
      setLoading(true);
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: "user", content: msg, timestamp: new Date().toISOString() },
      ]);
      const resposta = await sendMessage(msg, userType, produtorId);
      if (convGenRef.current !== gen) return;
      setMessages((m) => [...m, resposta]);
      onSessionStateChange?.(getSessionContextState(userType, produtorId));
      setLoading(false);
    },
    [loading, restaurando, userType, produtorId, onSessionStateChange]
  );

  useEffect(() => {
    if (!promptRequest || restaurando || loading) return;
    if (lastPromptIdRef.current === promptRequest.id) return;
    lastPromptIdRef.current = promptRequest.id;
    void enviar(promptRequest.text);
  }, [promptRequest, restaurando, loading, enviar]);

  async function limpar() {
    if (restaurando) return;
    convGenRef.current += 1;
    setLoading(false);
    const limpaPromise = clearConversation(userType, produtorId);
    setMessages(getConversationHistory(userType, produtorId));
    onSessionStateChange?.(null);
    await limpaPromise;
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
        <button className="btn-ghost" onClick={limpar} disabled={restaurando}>
          Nova conversa
        </button>
      </header>
      <div className="chat-body">
        {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
        {restaurando && (
          <div className="msg msg-bot">
            <span className="avatar">🌱</span>
            <div className="bubble typing">Sincronizando histórico salvo…</div>
          </div>
        )}
        {loading && (
          <div className="msg msg-bot">
            <span className="avatar">🌱</span>
            <div className="bubble typing">Consultando assistente…</div>
          </div>
        )}
        {!restaurando && messages.length <= 1 && (
          <div className="chips">
            {sugestoes[userType].map((s) => (
              <button key={s} className="chip" onClick={() => enviar(s)} disabled={loading}>
                {s}
              </button>
            ))}
          </div>
        )}
        <div ref={endRef} />
      </div>
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); void enviar(text); }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={restaurando ? "Sincronizando sessão…" : "Digite sua mensagem…"}
          aria-label="Mensagem"
        />
        <button
          type="submit"
          className="btn"
          disabled={!text.trim() || loading || restaurando}
          aria-label="Enviar"
        >
          ➤
        </button>
      </form>
    </section>
  );
}
