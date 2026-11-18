import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

<<<<<<< HEAD
const cert = process.env.KAIFIND_TLS_CERT;
const key = process.env.KAIFIND_TLS_KEY;
const apiOrigin = process.env.KAIFIND_API_ORIGIN ?? "http://127.0.0.1:8000";
if (Boolean(cert) !== Boolean(key)) {
  throw new Error("Set both KAIFIND_TLS_CERT and KAIFIND_TLS_KEY.");
}
=======
>>>>>>> 7594d95 (Dockerize frontend)
const server = {
  host: '0.0.0.0',
  port: 3000,
  strictPort: true,
<<<<<<< HEAD
  https:
    cert && key
      ? { cert: readFileSync(cert), key: readFileSync(key) }
      : undefined,
  proxy: { "^/api/v1(?:/|\\?|$)": apiOrigin },
=======
  allowedHosts: ['kaifind.pingsns.bond'],
  proxy: { "^/api/v1(?:/|\\?|$)": {
    target: "http://backend:8000", 
  } 
  },
>>>>>>> 7594d95 (Dockerize frontend)
};

export default defineConfig({ plugins: [react()], server, preview: server });
