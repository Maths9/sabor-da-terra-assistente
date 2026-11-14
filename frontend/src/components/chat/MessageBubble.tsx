import type { ChatMessage } from "../../types";

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`msg ${isUser ? "msg-user" : "msg-bot"}`}>
      {!isUser && <span className="avatar" aria-hidden>🌱</span>}
      <div className="bubble">{message.content}</div>
    </div>
  );
}
