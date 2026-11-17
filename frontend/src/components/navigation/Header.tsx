import type { UserType } from "../../types";

export type Area = UserType;

export default function Header({ area, onChange, onHome }: { area: Area; onChange: (a: Area) => void; onHome: () => void }) {
  return (
    <header className="topbar">
      <button className="brand" onClick={onHome}>🌱 Sabor da Terra</button>
      <nav className="switch" aria-label="Alternar perfil">
        <button className={area === "operador" ? "active" : ""} onClick={() => onChange("operador")}>Operador</button>
        <button className={area === "produtor" ? "active" : ""} onClick={() => onChange("produtor")}>Produtor</button>
      </nav>
    </header>
  );
}
