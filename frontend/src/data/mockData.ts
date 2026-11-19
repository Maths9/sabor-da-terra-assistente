import type { ProdutorListaItem, UserType } from "../types";

export const sugestoes: Record<UserType, string[]> = {
  operador: [
    "Quais pedidos pendentes temos na caixa de entrada hoje?",
    "Recebemos um pedido do SuperBom Atacado: 100kg de queijo coalho e 50kg de frango caipira. Podemos atender?",
    "O que diz o relatório da ADAGRO 2026 sobre não conformidades?",
    "Quais produtores têm certificação orgânica vigente hoje e quais produtos oferecem?",
  ],
  produtor: [
    "Qual é o meu resumo financeiro e de entregas desde setembro?",
    "Como está a validade da minha certificação orgânica e meu status de SIE?",
    "Tenho algum pagamento pendente ou aviso importante na cooperativa?",
    "Quais são as recomendações da ficha técnica para armazenamento dos meus produtos?",
  ],
};

export const boasVindas: Record<UserType, string> = {
  operador:
    "Olá! Sou o Assistente Sabor da Terra (perfil Operador). Posso fazer triagem de pedidos, consultar certificações/contratos/fichas técnicas no RAG, checar compliance sanitário e redigir rascunhos de notificação.",
  produtor:
    "Olá! Estou conectado à base real da Cooperativa Sabor da Terra. Posso consultar seus recebimentos, entregas, certificação e orientações técnicas (mantendo seus dados pessoais protegidos pela LGPD).",
};

export const produtoresFallback: ProdutorListaItem[] = [
  {
    id: "P001",
    nome: "Maria das Graças Silva Ferreira",
    municipio: "Garanhuns",
    produtos: ["goiaba", "acerola", "manga"],
    status: "ativo",
    certificacao_organica: "sim",
    validade_certificacao: "2027-06-15",
  },
];
