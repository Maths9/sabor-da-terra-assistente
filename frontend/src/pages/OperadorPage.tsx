import ChatWindow from "../components/chat/ChatWindow";

// Chat do Operador da Cooperativa — acesso operacional amplo (com proteção LGPD).
export default function OperadorPage() {
  return <main className="page-chat"><ChatWindow userType="operador" /></main>;
}
