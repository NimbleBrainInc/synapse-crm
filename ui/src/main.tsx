import "@nimblebrain/synapse/ui/base";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppProvider } from "@nimblebrain/synapse/react";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProvider name="crm" version="0.3.2">
      <App />
    </AppProvider>
  </StrictMode>,
);
