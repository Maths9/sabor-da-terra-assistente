import { useEffect, useState } from "react";
import Header from "./components/navigation/Header";
import ProfileSelect from "./pages/ProfileSelect";
import OperadorPage from "./pages/OperadorPage";
import OperatorLogin from "./pages/OperatorLogin";
import ProducerLogin from "./pages/ProducerLogin";
import ProducerPage from "./pages/ProducerPage";
import {
  fetchAuthConfig,
  getActiveAuthSession,
  loginPerfil,
  logoutAuthSession,
  setAuthExpiredHandler,
  verificarAuthSessao,
} from "./services/agentService";
import type { UserType } from "./types";

type View = "home" | "operador" | "operador-login" | "login" | "produtor";

export default function App() {
  const sessaoInicial = getActiveAuthSession();
  const [view, setView] = useState<View>(() => {
    if (sessaoInicial?.perfil === "operador") return "operador";
    if (sessaoInicial?.perfil === "produtor" && sessaoInicial.produtorId) return "produtor";
    return "home";
  });
  const [selectedProdutorId, setSelectedProdutorId] = useState<string | null>(
    sessaoInicial?.produtorId ?? null
  );
  const [requerCodigo, setRequerCodigo] = useState(false);
  const [validandoSessao, setValidandoSessao] = useState<boolean>(Boolean(sessaoInicial));
  const [authNotice, setAuthNotice] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;

    setAuthExpiredHandler((perfil) => {
      if (!ativo) return;
      setAuthNotice("Sua sessão expirou ou foi invalidada. Faça acesso novamente.");
      setView(perfil === "operador" ? "operador-login" : "login");
    });

    Promise.all([fetchAuthConfig(), sessaoInicial ? verificarAuthSessao() : Promise.resolve(null)])
      .then(([cfg, sessaoValidada]) => {
        if (!ativo) return;
        setRequerCodigo(Boolean(cfg.requer_codigo));
        if (sessaoInicial && !sessaoValidada) {
          setAuthNotice("Sua sessão anterior expirou. Informe o código de acesso novamente.");
          setView(sessaoInicial.perfil === "operador" ? "operador-login" : "login");
        }
      })
      .finally(() => {
        if (ativo) setValidandoSessao(false);
      });

    return () => {
      ativo = false;
      setAuthExpiredHandler(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const abrirOperador = async () => {
    setAuthNotice(null);
    const atual = getActiveAuthSession();
    if (atual?.perfil === "operador") {
      setView("operador");
      return;
    }
    if (requerCodigo) {
      setView("operador-login");
      return;
    }
    try {
      await loginPerfil("operador");
      setView("operador");
    } catch {
      setView("operador-login");
    }
  };

  const go = (a: UserType) => {
    setAuthNotice(null);
    if (a === "operador") {
      void abrirOperador();
      return;
    }
    const atual = getActiveAuthSession();
    if (view !== "home" && selectedProdutorId && atual?.perfil === "produtor") {
      setView("produtor");
      return;
    }
    setView("login");
  };

  const voltarInicio = () => {
    logoutAuthSession();
    setAuthNotice(null);
    setView("home");
  };

  if (validandoSessao) {
    return (
      <main className="center">
        <div className="card login">
          <strong>Validando sessão…</strong>
          <small>Verificando credenciais com o assistente da cooperativa.</small>
        </div>
      </main>
    );
  }

  return (
    <>
      {view !== "home" && (
        <Header
          area={view === "operador" || view === "operador-login" ? "operador" : "produtor"}
          onChange={go}
          onHome={voltarInicio}
        />
      )}
      {view === "home" && (
        <ProfileSelect
          onSelect={(a) => {
            setAuthNotice(null);
            if (a === "operador") {
              void abrirOperador();
            } else {
              setView("login");
            }
          }}
        />
      )}
      {view === "operador" && <OperadorPage />}
      {view === "operador-login" && (
        <OperatorLogin
          notice={authNotice}
          onEnter={() => {
            setAuthNotice(null);
            setView("operador");
          }}
          onBack={voltarInicio}
        />
      )}
      {view === "login" && (
        <ProducerLogin
          initialProdutorId={selectedProdutorId}
          notice={authNotice}
          onEnter={(id) => {
            setAuthNotice(null);
            setSelectedProdutorId(id);
            setView("produtor");
          }}
          onBack={voltarInicio}
        />
      )}
      {view === "produtor" && selectedProdutorId && (
        <ProducerPage
          produtorId={selectedProdutorId}
          onTrocarProdutor={() => {
            setAuthNotice(null);
            setView("login");
          }}
        />
      )}
    </>
  );
}
