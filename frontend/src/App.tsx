import { useState } from "react";
import Header from "./components/navigation/Header";
import ProfileSelect from "./pages/ProfileSelect";
import CooperadoPage from "./pages/CooperadoPage";
import ProducerLogin from "./pages/ProducerLogin";
import ProducerPage from "./pages/ProducerPage";

type View = "home" | "cooperado" | "login" | "produtor";

export default function App() {
  const [view, setView] = useState<View>("home");
  const go = (a: "cooperado" | "produtor") => setView(a === "cooperado" ? "cooperado" : "login");
  return (
    <>
      {view !== "home" && (
        <Header area={view === "cooperado" ? "cooperado" : "produtor"} onChange={go} onHome={() => setView("home")} />
      )}
      {view === "home" && <ProfileSelect onSelect={go} />}
      {view === "cooperado" && <CooperadoPage />}
      {view === "login" && <ProducerLogin onEnter={() => setView("produtor")} onBack={() => setView("cooperado")} />}
      {view === "produtor" && <ProducerPage />}
    </>
  );
}
