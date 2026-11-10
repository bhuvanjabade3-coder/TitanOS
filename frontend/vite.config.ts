/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const CORE = process.env.TITAN_CORE_URL ?? "http://127.0.0.1:8710";

// The dev server attaches the local API token server-side, so the token never
// reaches browser JavaScript. Read per request so core can start after Vite.
function token(): string | null {
  const dir =
    process.env.TITAN_DATA_DIR ??
    join(process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share"), "titan");
  try {
    return readFileSync(join(dir, "api_token"), "utf8").trim();
  } catch {
    return null;
  }
}

const attach = (proxy: any) => {
  const set = (req: any) => {
    const t = token();
    if (t) req.setHeader("Authorization", `Bearer ${t}`);
  };
  proxy.on("proxyReq", set);
  proxy.on("proxyReqWs", set);
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": { target: CORE, configure: attach },
      "/health": { target: CORE },
      "/ws": { target: CORE, ws: true, configure: attach },
    },
  },
  test: { environment: "jsdom", globals: true },
});
