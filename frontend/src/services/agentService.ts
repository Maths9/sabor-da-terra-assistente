// ============================================================================
// agentService — comunicação real com o backend FastAPI + Google ADK.
// ============================================================================
import type {
  ChatMessage,
  FonteDocumento,
  ProducerProfile,
  ProdutorListaItem,
  UserType,
} from "../types";
import { boasVindas } from "../data/mockData";

const API_BASE = ((import.meta as unknown as { env?: Record<string, string> }).env?.VITE_AGENT_API_URL || "").replace(
  /\/$/,
  ""
);

const historico: Record<string, ChatMessage[]> = {};
const sessoes: Record<string, string> = {};

function chaveSessao(userType: UserType, produtorId?: string): string {
  return userType === "produtor" && produtorId ? `produtor:${produtorId}` : userType;
}

function userIdParaContexto(userType: UserType, produtorId?: string): string {
  return userType === "produtor" && produtorId ? `produtor_${produtorId}` : "operador";
}

function obterOuCriarSessionId(chave: string): string {
  if (!sessoes[chave]) {
    sessoes[chave] = crypto.randomUUID();
  }
  return sessoes[chave];
}

const novaMsg = (
  role: ChatMessage["role"],
  content: string,
  extra?: { fontes?: FonteDocumento[]; erro?: boolean }
): ChatMessage => ({
  id: crypto.randomUUID(),
  role,
  content,
  timestamp: new Date().toISOString(),
  ...(extra?.fontes?.length ? { fontes: extra.fontes } : {}),
  ...(extra?.erro ? { erro: true } : {}),
});

export function getConversationHistory(userType: UserType, produtorId?: string): ChatMessage[] {
  const chave = chaveSessao(userType, produtorId);
  if (!historico[chave] || historico[chave].length === 0) {
    historico[chave] = [novaMsg("assistant", boasVindas[userType])];
  }
  return [...historico[chave]];
}

export async function sendMessage(
  message: string,
  userType: UserType,
  produtorId?: string
): Promise<ChatMessage> {
  const chave = chaveSessao(userType, produtorId);
  const userId = userIdParaContexto(userType, produtorId);
  const sessionId = obterOuCriarSessionId(chave);

  if (!historico[chave]) {
    historico[chave] = [novaMsg("assistant", boasVindas[userType])];
  }
  historico[chave].push(novaMsg("user", message));

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: sessionId,
        user_id: userId,
        user_type: userType,
        ...(userType === "produtor" && produtorId ? { produtor_id: produtorId } : {}),
      }),
    });

    if (!res.ok) {
      let detalhe = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        detalhe = errBody?.detail || detalhe;
      } catch {
        // Ignora corpo não JSON
      }
      throw new Error(detalhe);
    }

    const data = await res.json();
    if (data?.session_id) {
      sessoes[chave] = data.session_id;
    }

    const texto = data?.resposta || "Não recebi uma resposta do assistente.";
    const fontes: FonteDocumento[] = Array.isArray(data?.fontes) ? data.fontes : [];
    const resposta = novaMsg("assistant", texto, { fontes });
    historico[chave].push(resposta);
    return resposta;
  } catch (err) {
    const motivo = err instanceof Error ? err.message : "Erro de conexão com o servidor.";
    const msgErro = novaMsg(
      "assistant",
      `Não foi possível consultar o assistente no momento (${motivo}). Verifique se a API está em execução.`,
      { erro: true }
    );
    historico[chave].push(msgErro);
    return msgErro;
  }
}

export function clearConversation(userType: UserType, produtorId?: string): void {
  const chave = chaveSessao(userType, produtorId);
  const sessionAnterior = sessoes[chave];
  const userId = userIdParaContexto(userType, produtorId);

  historico[chave] = [];
  sessoes[chave] = crypto.randomUUID();

  if (sessionAnterior) {
    fetch(`${API_BASE}/api/sessoes/${encodeURIComponent(userId)}/${encodeURIComponent(sessionAnterior)}`, {
      method: "DELETE",
    }).catch(() => undefined);
  }
}

export async function fetchProdutores(): Promise<ProdutorListaItem[]> {
  const res = await fetch(`${API_BASE}/api/produtores`);
  if (!res.ok) {
    throw new Error(`Falha ao carregar produtores (HTTP ${res.status})`);
  }
  const data = await res.json();
  return Array.isArray(data?.produtores) ? data.produtores : [];
}

export async function fetchPainelProdutor(produtorId: string): Promise<ProducerProfile> {
  const res = await fetch(`${API_BASE}/api/produtores/${encodeURIComponent(produtorId)}`);
  if (!res.ok) {
    throw new Error(`Falha ao carregar painel do produtor ${produtorId} (HTTP ${res.status})`);
  }
  return res.json();
}
