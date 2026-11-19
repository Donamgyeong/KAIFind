import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const server = {
  host: '0.0.0.0',
  port: 3000,
  strictPort: true,
  allowedHosts: ['kaifind.pingsns.bond'],
  proxy: { "^/api/v1(?:/|\\?|$)": {
    target: "http://backend:8000", 
  } 
  },
};

export default defineConfig({ plugins: [react()], server, preview: server });
