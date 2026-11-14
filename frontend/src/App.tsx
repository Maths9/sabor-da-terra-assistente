import { useState } from "react";
import Header from "./components/navigation/Header";
import ProfileSelect from "./pages/ProfileSelect";
import CooperadoPage from "./pages/CooperadoPage";
import ProducerLogin from "./pages/ProducerLogin";
import ProducerPage from "./pages/ProducerPage";

type View = "home" | "cooperado" | "login" | "produtor";

export default function App() {
  const [view, setView] = useState<View>("home");
  const [selectedProdutorId, setSelectedProdutorId] = useState<string | null>(null);

  const go = (a: "cooperado" | "produtor") => {
    if (a === "cooperado") {
      setView("cooperado");
      return;
    }
    setView(view !== "home" && selectedProdutorId ? "produtor" : "login");
  };

  return (
    <>
      {view !== "home" && (
        <Header
          area={view === "cooperado" ? "cooperado" : "produtor"}
          onChange={go}
          onHome={() => setView("home")}
        />
      )}
      {view === "home" && <ProfileSelect onSelect={(a) => setView(a === "cooperado" ? "cooperado" : "login")} />}
      {view === "cooperado" && <CooperadoPage />}
      {view === "login" && (
        <ProducerLogin
          initialProdutorId={selectedProdutorId}
          onEnter={(id) => {
            setSelectedProdutorId(id);
            setView("produtor");
          }}
          onBack={() => setView("cooperado")}
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
