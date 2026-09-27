import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { BRAND } from "./brand";
// Self-hosted, split by character range: the browser downloads only the
// slices of each face that the page's text uses, and nothing leaves our origin.
import "@fontsource/noto-sans-tc/400.css";
import "@fontsource/noto-sans-tc/500.css";
import "@fontsource/noto-sans-tc/700.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./styles.css";

document.title = `${BRAND} · 班級報告`;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
