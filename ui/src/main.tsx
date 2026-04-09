import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SynapseProvider } from "@nimblebrain/synapse/react";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SynapseProvider name="crm" version="1.0.0">
      <App />
    </SynapseProvider>
  </StrictMode>,
);
