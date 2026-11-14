import type { ProducerProfile } from "../../types";

const Card = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="card"><h4>{title}</h4>{children}</div>
);

export default function InfoPanel({ p }: { p: ProducerProfile }) {
  return (
    <aside className="panel">
      <div className="card">
        <strong>{p.nome}</strong>
        <small>{p.codigo}</small>
        <span className="tag">{p.situacaoCadastral}</span>
      </div>
      <Card title="Avisos">
        {p.avisos.map((a) => <p key={a.id} className={`aviso ${a.nivel}`}>{a.texto}</p>)}
      </Card>
      <Card title="Pagamentos pendentes">
        <p className="big">{p.pagamentosPendentes.total}</p>
        {p.pagamentosPendentes.itens.map((i) => (
          <p key={i.descricao} className="row"><span>{i.descricao} · {i.previsao}</span><span>{i.valor}</span></p>
        ))}
      </Card>
      <Card title="Certificação">
        <p className="row"><span>{p.certificacao.tipo}</span><span>até {p.certificacao.validade}</span></p>
        <small>{p.certificacao.diasRestantes} dias restantes</small>
      </Card>
      <Card title="Produtos fornecidos">
        <div className="tags">{p.produtos.map((x) => <span key={x} className="tag">{x}</span>)}</div>
      </Card>
      <Card title="Últimas movimentações">
        {p.movimentacoes.map((m) => <p key={m.data + m.descricao} className="row"><span>{m.data} · {m.descricao}</span><span>{m.valor}</span></p>)}
      </Card>
    </aside>
  );
}
