export default function ProfileSelect({ onSelect }: { onSelect: (a: "cooperado" | "produtor") => void }) {
  return (
    <main className="center">
      <h1>Assistente Sabor da Terra</h1>
      <p className="muted">Escolha como deseja acessar o assistente da cooperativa.</p>
      <div className="grid2">
        <button className="choice" onClick={() => onSelect("cooperado")}><span>👤</span><strong>Sou cooperado</strong><small>Converse com o assistente</small></button>
        <button className="choice" onClick={() => onSelect("produtor")}><span>🌾</span><strong>Sou produtor</strong><small>Acessar área do produtor</small></button>
      </div>
    </main>
  );
}
