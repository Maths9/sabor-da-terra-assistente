import ChatWindow from "../components/chat/ChatWindow";

// Chat tradicional — sem painel lateral.
export default function CooperadoPage() {
  return <main className="page-chat"><ChatWindow userType="cooperado" /></main>;
}
