export type UserType = "cooperado" | "produtor";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string; // ISO
}

export interface ProducerProfile {
  nome: string;
  codigo: string;
  situacaoCadastral: "Ativo" | "Pendente" | "Inativo";
  produtos: string[];
  certificacao: { tipo: string; validade: string; diasRestantes: number };
  pagamentosPendentes: { total: string; itens: { descricao: string; valor: string; previsao: string }[] };
  movimentacoes: { data: string; descricao: string; valor: string }[];
  avisos: { id: string; texto: string; nivel: "info" | "atencao" }[];
}
