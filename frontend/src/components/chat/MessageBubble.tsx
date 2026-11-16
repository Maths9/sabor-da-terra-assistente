import type { ChatMessage } from "../../types";
import MarkdownContent from "./MarkdownContent";

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const fontes = !isUser && message.fontes?.length ? message.fontes : [];

  return (
    <div className={`msg ${isUser ? "msg-user" : "msg-bot"}`}>
      {!isUser && <span className="avatar" aria-hidden>🌱</span>}
      <div className={`bubble${message.erro ? " bubble-error" : ""}`}>
        {isUser ? (
          <div className="msg-plain">{message.content}</div>
        ) : (
          <MarkdownContent content={message.content} />
        )}
        {fontes.length > 0 && (
          <div className="fontes">
            <small>Fontes consultadas:</small>
            <div className="fontes-list">
              {fontes.map((f, idx) => (
                <span key={`${f.documento_id}-${idx}`} className="fonte-tag" title={f.referencia}>
                  {f.nome}
                  {f.localizacao ? ` (${f.localizacao})` : ""}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
