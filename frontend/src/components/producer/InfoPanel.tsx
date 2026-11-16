import type { ProducerProfile } from "../../types";

const Card = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="card"><h4>{title}</h4>{children}</div>
);

interface InfoPanelProps {
  p: ProducerProfile;
  onTrocarProdutor?: () => void;
}

export default function InfoPanel({ p, onTrocarProdutor }: InfoPanelProps) {
  const temValidade = p.certificacao.validade && p.certificacao.validade !== "—";
  let detalhePrazo = "";
  if (temValidade) {
    if (p.certificacao.diasRestantes > 0) {
      detalhePrazo = `${p.certificacao.diasRestantes} dias restantes`;
    } else if (p.certificacao.diasRestantes === 0) {
      detalhePrazo = "Vence hoje";
    } else {
      detalhePrazo = `Vencida há ${Math.abs(p.certificacao.diasRestantes)} dias`;
    }
  }

  return (
    <aside className="panel">
      <div className="card">
        <strong>{p.nome}</strong>
        <small>
          {p.codigo}
          {p.municipio ? ` · ${p.municipio}` : ""}
        </small>
        <span className="tag">{p.situacaoCadastral}</span>
        {onTrocarProdutor && (
          <button type="button" className="btn-ghost wide panel-switch-btn" onClick={onTrocarProdutor}>
            Trocar produtor
          </button>
        )}
      </div>
      <Card title="Avisos">
        {p.avisos.length > 0 ? (
          p.avisos.map((a) => <p key={a.id} className={`aviso ${a.nivel}`}>{a.texto}</p>)
        ) : (
          <small>Nenhum aviso ativo.</small>
        )}
      </Card>
      <Card title="Pagamentos pendentes">
        <p className="big">{p.pagamentosPendentes.total}</p>
        {p.pagamentosPendentes.itens.length > 0 ? (
          p.pagamentosPendentes.itens.map((i, idx) => (
            <p key={`${i.descricao}-${idx}`} className="row">
              <span>{i.descricao} · {i.previsao}</span>
              <span>{i.valor}</span>
            </p>
          ))
        ) : (
          <small>Nenhum pagamento pendente.</small>
        )}
      </Card>
      <Card title="Certificação">
        <p className="row">
          <span>{p.certificacao.tipo}</span>
          <span>{temValidade ? `até ${p.certificacao.validade}` : "Sem validade"}</span>
        </p>
        {(p.certificacao.situacao || detalhePrazo) && (
          <small>
            {[p.certificacao.situacao, detalhePrazo].filter(Boolean).join(" · ")}
          </small>
        )}
      </Card>
      <Card title="Produtos fornecidos">
        {p.produtos.length > 0 ? (
          <div className="tags">{p.produtos.map((x) => <span key={x} className="tag">{x}</span>)}</div>
        ) : (
          <small>Nenhum produto cadastrado.</small>
        )}
      </Card>
      <Card title="Últimas movimentações">
        {p.movimentacoes.length > 0 ? (
          p.movimentacoes.map((m, idx) => (
            <p key={`${m.data}-${m.descricao}-${idx}`} className="row">
              <span>{m.data} · {m.descricao}</span>
              <span>{m.valor}</span>
            </p>
          ))
        ) : (
          <small>Sem movimentações registradas.</small>
        )}
      </Card>
    </aside>
  );
}
