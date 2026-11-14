// ============================================================================
// agentService — ÚNICO ponto de comunicação com o agente de IA.
// Hoje: SIMULADO (sem rede). Para integrar, substitua apenas o corpo das funções.
// ============================================================================
import type { ChatMessage, UserType } from "../types";
import { boasVindas, respostaPadrao, respostasSimuladas } from "../data/mockData";

// TODO (integração futura): configurar a URL do backend, ex.:
// const API_URL = import.meta.env.VITE_AGENT_API_URL;

const historico: Record<UserType, ChatMessage[]> = { cooperado: [], produtor: [] };
const novaMsg = (role: ChatMessage["role"], content: string): ChatMessage => ({
  id: crypto.randomUUID(), role, content, timestamp: new Date().toISOString(),
});

export function getConversationHistory(userType: UserType): ChatMessage[] {
  // TODO (integração futura): buscar o histórico no backend.
  if (historico[userType].length === 0) historico[userType].push(novaMsg("assistant", boasVindas[userType]));
  return [...historico[userType]];
}

export async function sendMessage(message: string, userType: UserType): Promise<ChatMessage> {
  historico[userType].push(novaMsg("user", message));

  // TODO (integração futura): CHAMADA AO AGENTE — ex.:
  // const res = await fetch(`${API_URL}/chat`, { method: "POST", headers: {...}, body: JSON.stringify({ message, userType }) });
  // const { reply } = await res.json();

  // --- SIMULAÇÃO LOCAL (remover ao integrar) ---
  await new Promise((r) => setTimeout(r, 700));
  const texto = message.toLowerCase();
  const reply = respostasSimuladas.find((r) => r.chaves.some((c) => texto.includes(c)))?.resposta ?? respostaPadrao;
  // ----------------------------------------------

  const resposta = novaMsg("assistant", reply);
  historico[userType].push(resposta);
  return resposta;
}

export function clearConversation(userType: UserType): void {
  // TODO (integração futura): encerrar/limpar a sessão no backend.
  historico[userType] = [];
}
