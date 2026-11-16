export type UserType = "cooperado" | "produtor";

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
