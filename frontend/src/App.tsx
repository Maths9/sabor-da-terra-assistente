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

  useEffect(() => {
    fetchAuthConfig().then((cfg) => setRequerCodigo(Boolean(cfg.requer_codigo)));
  }, []);

  const abrirOperador = async () => {
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
    setView("home");
  };

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
          onEnter={() => setView("operador")}
          onBack={voltarInicio}
        />
      )}
      {view === "login" && (
        <ProducerLogin
          initialProdutorId={selectedProdutorId}
          onEnter={(id) => {
            setSelectedProdutorId(id);
            setView("produtor");
          }}
          onBack={voltarInicio}
        />
      )}
      {view === "produtor" && selectedProdutorId && (
        <ProducerPage
          produtorId={selectedProdutorId}
          onTrocarProdutor={() => setView("login")}
        />
      )}
    </>
  );
}
