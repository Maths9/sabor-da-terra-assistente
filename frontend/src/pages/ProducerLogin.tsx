// Acesso SIMULADO: sem validação de senha nem autenticação real.
export default function ProducerLogin({ onEnter, onBack }: { onEnter: () => void; onBack: () => void }) {
  return (
    <main className="center">
      <div className="card login">
        <h2>Área do produtor</h2>
        <p className="muted">Acesso demonstrativo, sem autenticação real.</p>
        <input placeholder="Identificação (demonstrativo)" disabled />
        <input type="password" placeholder="Senha (demonstrativa)" disabled />
        <button className="btn wide" onClick={onEnter}>Entrar como produtor</button>
        <button className="btn-ghost wide" onClick={onBack}>Voltar à área do cooperado</button>
      </div>
    </main>
  );
}
