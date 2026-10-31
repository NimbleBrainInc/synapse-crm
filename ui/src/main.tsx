import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppProvider } from "@nimblebrain/synapse/react";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProvider name="crm" version="1.0.0" forwardKeys>
      <App />
    </AppProvider>
  </StrictMode>,
);
