export type UserType = "operador" | "produtor";

export interface AuthConfig {
  requer_codigo: boolean;
  perfis_disponiveis: UserType[];
}

export interface AuthSession {
  accessToken: string;
  userId: string;
  perfil: UserType;
  produtorId?: string | null;
}

export interface HealthStatus {
  status: string;
  agent?: string;
}

export interface PedidoPendenteResumo {
  id: string;
  data_recebimento: string;
  canal: string;
  comprador: string;
  status: string;
}

export interface UltimoPedidoResumo {
  id_pedido?: string | null;
  comprador?: string | null;
  canal?: string | null;
  data_referencia?: string | null;
  mes_entrega?: number | null;
  status_viabilidade?: string | null;
  campos_pendentes?: string[];
  valor_total_estimado?: number | null;
}

export interface ResultadoTriagemResumo {
  id_pedido?: string | null;
  remetente_identificado?: string | null;
  tipo_cliente?: string | null;
  tipo_demanda?: string | null;
  urgencia?: string | null;
  status_viabilidade?: string | null;
  campos_pendentes?: string[];
  valor_total_estimado?: number | null;
  resumo_executivo_triagem?: string | null;
}

export interface SessionContextState {
  produtorEmFoco: string | null;
  ultimoPedido: UltimoPedidoResumo | null;
  resultadoTriagem: ResultadoTriagemResumo | null;
}

export interface FonteDocumento {
  documento_id: string;
  nome: string;
  localizacao?: string | null;
  referencia: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string; // ISO
  fontes?: FonteDocumento[];
  erro?: boolean;
}

export interface ProdutorListaItem {
  id: string;
  nome: string;
  municipio: string;
  produtos: string[];
  status: string;
  certificacao_organica: string;
  validade_certificacao?: string | null;
}

export interface ProducerProfile {
  nome: string;
  codigo: string;
  municipio?: string;
  situacaoCadastral: "Ativo" | "Pendente" | "Inativo";
  produtos: string[];
  certificacao: {
    tipo: string;
    situacao?: string;
    validade: string;
    diasRestantes: number;
  };
  pagamentosPendentes: {
    total: string;
    itens: { descricao: string; valor: string; previsao: string }[];
  };
  movimentacoes: { data: string; descricao: string; valor: string }[];
  avisos: { id: string; texto: string; nivel: "info" | "atencao" }[];
}
