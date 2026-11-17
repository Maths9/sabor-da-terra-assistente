import type { UserType } from "../types";

export default function ProfileSelect({ onSelect }: { onSelect: (a: UserType) => void }) {
  return (
    <main className="center">
      <h1>Assistente Sabor da Terra</h1>
      <p className="muted">Escolha seu perfil de acesso ao assistente da cooperativa.</p>
      <div className="grid2">
        <button className="choice" onClick={() => onSelect("operador")}>
          <span>👤</span>
          <strong>Sou operador</strong>
          <small>Gestão, triagem e atendimento</small>
        </button>
        <button className="choice" onClick={() => onSelect("produtor")}>
          <span>🌾</span>
          <strong>Sou produtor</strong>
          <small>Acessar área do produtor</small>
        </button>
      </div>
    </main>
  );
}
