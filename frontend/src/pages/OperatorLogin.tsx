import { useState } from "react";
import { loginPerfil } from "../services/agentService";

interface OperatorLoginProps {
  notice?: string | null;
  onEnter: () => void;
  onBack: () => void;
}

export default function OperatorLogin({ notice, onEnter, onBack }: OperatorLoginProps) {
  const [codigo, setCodigo] = useState("");
  const [entrando, setEntrando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function entrar(e: React.FormEvent) {
    e.preventDefault();
    if (entrando) return;
    setEntrando(true);
    setErro(null);
    try {
      await loginPerfil("operador", undefined, codigo);
      onEnter();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao autenticar operador.");
    } finally {
      setEntrando(false);
    }
  }

  return (
    <main className="center">
      <form className="card login" onSubmit={entrar}>
        <h2>Área do Operador</h2>
        <p className="muted">
          Informe o código de acesso da equipe operacional da cooperativa.
        </p>
        {notice && <p className="aviso atencao">{notice}</p>}
        <label htmlFor="operador-codigo">
          <small>Código de acesso</small>
        </label>
        <input
          id="operador-codigo"
          type="password"
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          placeholder="Digite o código de acesso"
          autoFocus
        />
        {erro && <p className="aviso atencao">{erro}</p>}
        <button type="submit" className="btn wide" disabled={!codigo.trim() || entrando}>
          {entrando ? "Validando…" : "Entrar como operador"}
        </button>
        <button type="button" className="btn-ghost wide" onClick={onBack}>
          Voltar ao início
        </button>
      </form>
    </main>
  );
}
