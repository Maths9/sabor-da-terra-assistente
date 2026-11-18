// ============================================================================
// agentService — comunicação autenticada com o backend FastAPI + Google ADK.
// ============================================================================
import type {
  AuthConfig,
  AuthSession,
  ChatMessage,
  FonteDocumento,
  HealthStatus,
  PedidoPendenteResumo,
  ProducerProfile,
  ProdutorListaItem,
  ResultadoTriagemResumo,
  SessionContextState,
  UltimoPedidoResumo,
  UserType,
} from "../types";
import { boasVindas } from "../data/mockData";

const API_BASE = ((import.meta as unknown as { env?: Record<string, string> }).env?.VITE_AGENT_API_URL || "").replace(
  /\/$/,
  ""
);

const STORAGE_AUTH_KEY = "sabor_da_terra.auth_session";
const STORAGE_SESSOES_KEY = "sabor_da_terra.session_ids";

const historico: Record<string, ChatMessage[]> = {};
const estadoSessao: Record<string, SessionContextState | null> = {};
const geracaoConversa: Record<string, number> = {};
const deletesEmAndamento: Record<string, Promise<void> | undefined> = {};

let sessoes: Record<string, string> = carregarSessoesStorage();
let authAtual: AuthSession | null = carregarAuthStorage();
let authConfigCache: AuthConfig | null = null;
let authExpiredHandler: ((perfil: UserType) => void) | null = null;

function carregarSessoesStorage(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_SESSOES_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return parsed as Record<string, string>;
      }
    }
  } catch {
    // Ignora indisponibilidade de storage
  }
  return {};
}

function salvarSessoesStorage(): void {
  try {
    localStorage.setItem(STORAGE_SESSOES_KEY, JSON.stringify(sessoes));
  } catch {
    // Ignora indisponibilidade de storage
  }
}

function carregarAuthStorage(): AuthSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_AUTH_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthSession;
    if (parsed?.accessToken && parsed?.perfil && parsed?.userId) {
      return parsed;
    }
  } catch {
    // Ignora indisponibilidade de storage
  }
  return null;
}

function salvarAuthStorage(sess: AuthSession | null): void {
  authAtual = sess;
  try {
    if (sess) {
      localStorage.setItem(STORAGE_AUTH_KEY, JSON.stringify(sess));
    } else {
      localStorage.removeItem(STORAGE_AUTH_KEY);
    }
  } catch {
    // Ignora indisponibilidade de storage
  }
}

function chaveSessao(userType: UserType, produtorId?: string): string {
  return userType === "produtor" && produtorId ? `produtor:${produtorId.toUpperCase()}` : "operador";
}

function userIdParaContexto(userType: UserType, produtorId?: string): string {
  return userType === "produtor" && produtorId ? `produtor_${produtorId.toUpperCase()}` : "operador";
}

function obterOuCriarSessionId(chave: string): string {
  if (!sessoes[chave]) {
    sessoes[chave] = crypto.randomUUID();
    salvarSessoesStorage();
  }
  return sessoes[chave];
}

function definirSessionId(chave: string, sessionId: string): void {
  if (sessoes[chave] !== sessionId) {
    sessoes[chave] = sessionId;
    salvarSessoesStorage();
  }
}

function incrementarGeracao(chave: string): number {
  const prox = (geracaoConversa[chave] ?? 0) + 1;
  geracaoConversa[chave] = prox;
  return prox;
}

function extrairEstadoSessao(raw: unknown): SessionContextState | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const focoRaw = obj.produtor_em_foco;
  let produtorEmFoco: string | null = null;
  if (typeof focoRaw === "string" && focoRaw.trim()) {
    produtorEmFoco = focoRaw.trim();
  } else if (focoRaw && typeof focoRaw === "object") {
    const pid = (focoRaw as Record<string, unknown>).produtor_id;
    if (typeof pid === "string" && pid.trim()) produtorEmFoco = pid.trim();
  }

  const ultimoPedido =
    obj.ultimo_pedido && typeof obj.ultimo_pedido === "object"
      ? (obj.ultimo_pedido as UltimoPedidoResumo)
      : null;
  const resultadoTriagem =
    obj.resultado_triagem && typeof obj.resultado_triagem === "object"
      ? (obj.resultado_triagem as ResultadoTriagemResumo)
      : null;

  if (!produtorEmFoco && !ultimoPedido && !resultadoTriagem) {
    return null;
  }
  return { produtorEmFoco, ultimoPedido, resultadoTriagem };
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

export function setAuthExpiredHandler(handler: ((perfil: UserType) => void) | null): void {
  authExpiredHandler = handler;
}

export function getActiveAuthSession(): AuthSession | null {
  return authAtual;
}

export function logoutAuthSession(): void {
  salvarAuthStorage(null);
}

export function getSessionContextState(userType: UserType, produtorId?: string): SessionContextState | null {
  return estadoSessao[chaveSessao(userType, produtorId)] ?? null;
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) {
    throw new Error(`API indisponível (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchAuthConfig(forceRefresh = false): Promise<AuthConfig> {
  if (authConfigCache && !forceRefresh) return authConfigCache;
  try {
    const res = await fetch(`${API_BASE}/api/auth/config`);
    if (res.ok) {
      const data = (await res.json()) as AuthConfig;
      authConfigCache = data;
      return data;
    }
  } catch {
    // Fallback em caso de offline inicial
  }
  return authConfigCache ?? { requer_codigo: false, perfis_disponiveis: ["operador", "produtor"] };
}

export async function loginPerfil(
  perfil: UserType,
  produtorId?: string,
  codigoAcesso?: string
): Promise<AuthSession> {
  const res = await fetch(`${API_BASE}/api/auth/sessao`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      perfil,
      ...(perfil === "produtor" && produtorId ? { produtor_id: produtorId.toUpperCase() } : {}),
      ...(codigoAcesso ? { codigo_acesso: codigoAcesso } : {}),
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
  const sessao: AuthSession = {
    accessToken: data.access_token,
    userId: data.user_id,
    perfil: data.perfil,
    produtorId: data.produtor_id ?? null,
  };
  salvarAuthStorage(sessao);
  return sessao;
}

export async function verificarAuthSessao(): Promise<AuthSession | null> {
  if (!authAtual) return null;
  const atual = authAtual;
  try {
    const res = await fetch(`${API_BASE}/api/auth/sessao`, {
      method: "GET",
      headers: { Authorization: `Bearer ${atual.accessToken}` },
    });
    if (res.ok) {
      const info = await res.json();
      const confirmada: AuthSession = {
        accessToken: atual.accessToken,
        userId: info.user_id ?? atual.userId,
        perfil: info.perfil ?? atual.perfil,
        produtorId: info.produtor_id ?? atual.produtorId ?? null,
      };
      salvarAuthStorage(confirmada);
      return confirmada;
    }
    if (res.status === 401) {
      const cfg = await fetchAuthConfig(true);
      salvarAuthStorage(null);
      if (!cfg.requer_codigo) {
        return await loginPerfil(atual.perfil, atual.produtorId ?? undefined);
      }
      return null;
    }
  } catch {
    // Em falha de rede momentânea, mantém o estado local até nova tentativa
    return atual;
  }
  return atual;
}

function authCorresponde(sess: AuthSession | null, userType: UserType, produtorId?: string): boolean {
  if (!sess) return false;
  if (sess.perfil !== userType) return false;
  if (userType === "produtor") {
    return (sess.produtorId || "").toUpperCase() === (produtorId || "").toUpperCase();
  }
  return true;
}

async function garantirAuth(userType: UserType, produtorId?: string): Promise<AuthSession> {
  if (authCorresponde(authAtual, userType, produtorId) && authAtual) {
    return authAtual;
  }
  const cfg = await fetchAuthConfig();
  if (cfg.requer_codigo) {
    authExpiredHandler?.(userType);
    throw new Error("Autenticação com código de acesso necessária para este perfil.");
  }
  return loginPerfil(userType, produtorId);
}

async function authFetch(
  path: string,
  init: RequestInit,
  userType: UserType,
  produtorId?: string
): Promise<Response> {
  let sess = await garantirAuth(userType, produtorId);
  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${sess.accessToken}`);

  let res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    const cfg = await fetchAuthConfig(true);
    salvarAuthStorage(null);
    if (!cfg.requer_codigo) {
      sess = await loginPerfil(userType, produtorId);
      const retryHeaders = new Headers(init.headers || {});
      retryHeaders.set("Authorization", `Bearer ${sess.accessToken}`);
      res = await fetch(`${API_BASE}${path}`, { ...init, headers: retryHeaders });
    } else {
      authExpiredHandler?.(userType);
    }
  }
  return res;
}

export function getConversationHistory(userType: UserType, produtorId?: string): ChatMessage[] {
  const chave = chaveSessao(userType, produtorId);
  if (!historico[chave] || historico[chave].length === 0) {
    historico[chave] = [novaMsg("assistant", boasVindas[userType])];
  }
  return [...historico[chave]];
}

export async function restoreConversation(
  userType: UserType,
  produtorId?: string
): Promise<ChatMessage[]> {
  const chave = chaveSessao(userType, produtorId);
  const userId = userIdParaContexto(userType, produtorId);

  const deletePendente = deletesEmAndamento[chave];
  if (deletePendente) {
    await deletePendente;
  }

  const geracaoInicial = geracaoConversa[chave] ?? 0;

  try {
    await garantirAuth(userType, produtorId);
    let sessionId = sessoes[chave];
    let detalheRes: Response | null = null;

    if (sessionId) {
      detalheRes = await authFetch(
        `/api/sessoes/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}`,
        { method: "GET" },
        userType,
        produtorId
      );
      if (detalheRes.status === 404) {
        detalheRes = null;
      }
    }

    if (!detalheRes) {
      const listaRes = await authFetch("/api/sessoes", { method: "GET" }, userType, produtorId);
      if (listaRes.ok) {
        const listaBody = await listaRes.json();
        const sessoesApi = Array.isArray(listaBody?.sessoes) ? listaBody.sessoes : [];
        if (sessoesApi.length > 0 && sessoesApi[0]?.session_id) {
          sessionId = String(sessoesApi[0].session_id);
          if ((geracaoConversa[chave] ?? 0) === geracaoInicial) {
            definirSessionId(chave, sessionId);
          }
          detalheRes = await authFetch(
            `/api/sessoes/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}`,
            { method: "GET" },
            userType,
            produtorId
          );
        }
      }
    }

    if ((geracaoConversa[chave] ?? 0) !== geracaoInicial) {
      return getConversationHistory(userType, produtorId);
    }

    if (detalheRes && detalheRes.ok) {
      const detalhe = await detalheRes.json();
      if ((geracaoConversa[chave] ?? 0) !== geracaoInicial) {
        return getConversationHistory(userType, produtorId);
      }
      estadoSessao[chave] = extrairEstadoSessao(detalhe?.state);
      const mensagensBackend: ChatMessage[] = Array.isArray(detalhe?.mensagens)
        ? detalhe.mensagens.map((m: ChatMessage) => ({
            id: m.id || crypto.randomUUID(),
            role: m.role,
            content: m.content,
            timestamp: m.timestamp || new Date().toISOString(),
            ...(Array.isArray(m.fontes) && m.fontes.length ? { fontes: m.fontes } : {}),
          }))
        : [];
      historico[chave] =
        mensagensBackend.length > 0
          ? [novaMsg("assistant", boasVindas[userType]), ...mensagensBackend]
          : [novaMsg("assistant", boasVindas[userType])];
      return [...historico[chave]];
    }
  } catch {
    // Se offline ou sem sessão persistida ainda, mantém boas-vindas locais
  }

  return getConversationHistory(userType, produtorId);
}

export async function sendMessage(
  message: string,
  userType: UserType,
  produtorId?: string
): Promise<ChatMessage> {
  const chave = chaveSessao(userType, produtorId);
  const deletePendente = deletesEmAndamento[chave];
  if (deletePendente) {
    await deletePendente;
  }

  const geracaoEnvio = incrementarGeracao(chave);
  const sessionId = obterOuCriarSessionId(chave);

  if (!historico[chave] || historico[chave].length === 0) {
    historico[chave] = [novaMsg("assistant", boasVindas[userType])];
  }
  historico[chave].push(novaMsg("user", message));

  try {
    const res = await authFetch(
      "/api/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          user_type: userType,
          ...(userType === "produtor" && produtorId ? { produtor_id: produtorId.toUpperCase() } : {}),
        }),
      },
      userType,
      produtorId
    );

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
    const texto = data?.resposta || "Não recebi uma resposta do assistente.";
    const fontes: FonteDocumento[] = Array.isArray(data?.fontes) ? data.fontes : [];
    const resposta = novaMsg("assistant", texto, { fontes });

    if ((geracaoConversa[chave] ?? 0) === geracaoEnvio) {
      if (data?.session_id) {
        definirSessionId(chave, data.session_id);
      }
      estadoSessao[chave] = extrairEstadoSessao(data);
      historico[chave].push(resposta);
    }
    return resposta;
  } catch (err) {
    const motivo = err instanceof Error ? err.message : "Erro de conexão com o servidor.";
    const msgErro = novaMsg(
      "assistant",
      `Não foi possível consultar o assistente no momento (${motivo}). Verifique se a API está em execução.`,
      { erro: true }
    );
    if ((geracaoConversa[chave] ?? 0) === geracaoEnvio) {
      historico[chave].push(msgErro);
    }
    return msgErro;
  }
}

export async function clearConversation(userType: UserType, produtorId?: string): Promise<void> {
  const chave = chaveSessao(userType, produtorId);
  const sessionAnterior = sessoes[chave];
  const userId = userIdParaContexto(userType, produtorId);

  incrementarGeracao(chave);
  historico[chave] = [];
  estadoSessao[chave] = null;
  definirSessionId(chave, crypto.randomUUID());

  if (sessionAnterior) {
    const op = authFetch(
      `/api/sessoes/${encodeURIComponent(userId)}/${encodeURIComponent(sessionAnterior)}`,
      { method: "DELETE" },
      userType,
      produtorId
    )
      .then(() => undefined)
      .catch(() => undefined)
      .finally(() => {
        if (deletesEmAndamento[chave] === op) {
          delete deletesEmAndamento[chave];
        }
      });
    deletesEmAndamento[chave] = op;
    await op;
  }
}

export async function fetchPedidosPendentes(): Promise<PedidoPendenteResumo[]> {
  const res = await authFetch("/api/pedidos-pendentes", { method: "GET" }, "operador");
  if (!res.ok) {
    let detalhe = `HTTP ${res.status}`;
    try {
      const errBody = await res.json();
      detalhe = errBody?.detail || detalhe;
    } catch {
      // Ignora corpo não JSON
    }
    throw new Error(`Falha ao carregar caixa de pedidos (${detalhe})`);
  }
  const body = await res.json();
  const pedidos = body?.dados?.pedidos;
  return Array.isArray(pedidos) ? pedidos : [];
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
  const res = await authFetch(
    `/api/produtores/${encodeURIComponent(produtorId)}`,
    { method: "GET" },
    "produtor",
    produtorId
  );
  if (!res.ok) {
    let detalhe = `HTTP ${res.status}`;
    try {
      const errBody = await res.json();
      detalhe = errBody?.detail || detalhe;
    } catch {
      // Ignora corpo não JSON
    }
    throw new Error(`Falha ao carregar painel do produtor ${produtorId} (${detalhe})`);
  }
  return res.json();
}
