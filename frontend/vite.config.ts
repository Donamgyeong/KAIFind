import { readFileSync } from "node:fs";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const cert = process.env.KAIFIND_TLS_CERT;
const key = process.env.KAIFIND_TLS_KEY;
if (Boolean(cert) !== Boolean(key)) {
  throw new Error("Set both KAIFIND_TLS_CERT and KAIFIND_TLS_KEY.");
}
const server = {
  port: 3000,
  strictPort: true,
  https:
    cert && key
      ? { cert: readFileSync(cert), key: readFileSync(key) }
      : undefined,
  proxy: { "^/api/v1(?:/|\\?|$)": "http://127.0.0.1:8000" },
};

export default defineConfig({ plugins: [react()], server, preview: server });
