// DADOS FICTÍCIOS — nenhum dado real. Serão substituídos pela API no futuro.
import type { ProducerProfile, UserType } from "../types";

export const sugestoes: Record<UserType, string[]> = {
  cooperado: [
    "Quais produtos estão disponíveis?",
    "Como está a situação dos meus pagamentos?",
    "Quais são os preços dos produtos?",
    "Existe alguma atualização sobre meus pedidos?",
  ],
  produtor: [
    "Quanto tenho a receber?",
    "Como está a validade da minha certificação?",
    "Quais foram minhas últimas vendas?",
    "Quais produtos estão cadastrados?",
    "Existem pendências relacionadas aos meus documentos?",
  ],
};

export const boasVindas: Record<UserType, string> = {
  cooperado: "Olá! Sou o Assistente Sabor da Terra. Posso ajudar com produtos, preços, pagamentos e pedidos. Como posso ajudar?",
  produtor: "Olá, produtor! Posso consultar seus recebimentos, certificação, vendas e documentos. O que deseja saber?",
};

// Respostas demonstrativas por palavra-chave (usadas apenas pelo agentService simulado)
export const respostasSimuladas: { chaves: string[]; resposta: string }[] = [
  { chaves: ["receber", "pagamento"], resposta: "Valores fictícios: há R$ 3.250,00 previstos para os próximos 15 dias, em 2 lançamentos." },
  { chaves: ["certifica"], resposta: "Sua certificação orgânica (fictícia) vence em 47 dias. Recomendo iniciar a renovação em breve." },
  { chaves: ["venda"], resposta: "Últimas vendas (fictícias): 120 kg de tomate, 80 kg de alface e 45 kg de cenoura." },
  { chaves: ["produto", "preço", "preco"], resposta: "Produtos de exemplo: tomate (R$ 6,50/kg), alface (R$ 3,00/un.), cenoura (R$ 4,20/kg) e mandioca (R$ 5,00/kg)." },
  { chaves: ["pedido"], resposta: "Seu pedido #1042 (fictício) está em separação e deve ser entregue em 2 dias úteis." },
  { chaves: ["documento", "pendência", "pendencia"], resposta: "Há 1 pendência fictícia: comprovante de análise de solo a ser atualizado." },
];
export const respostaPadrao = "Esta é uma resposta demonstrativa. Em breve, o agente de IA responderá com informações reais.";

export const produtorMock: ProducerProfile = {
  nome: "Maria das Dores (fictício)",
  codigo: "PROD-0042",
  situacaoCadastral: "Ativo",
  produtos: ["Tomate", "Alface", "Cenoura", "Mandioca"],
  certificacao: { tipo: "Orgânica", validade: "30/12/2026", diasRestantes: 47 },
  pagamentosPendentes: {
    total: "R$ 3.250,00",
    itens: [
      { descricao: "Entrega 18/11", valor: "R$ 1.800,00", previsao: "20/11" },
      { descricao: "Entrega 25/11", valor: "R$ 1.450,00", previsao: "27/11" },
    ],
  },
  movimentacoes: [
    { data: "10/11", descricao: "Venda — Tomate 120 kg", valor: "+ R$ 780,00" },
    { data: "07/11", descricao: "Venda — Alface 80 un.", valor: "+ R$ 240,00" },
    { data: "03/11", descricao: "Taxa da cooperativa", valor: "- R$ 45,00" },
  ],
  avisos: [
    { id: "a1", texto: "Certificação vence em 47 dias.", nivel: "atencao" },
    { id: "a2", texto: "Reunião da cooperativa dia 20/11.", nivel: "info" },
  ],
};
