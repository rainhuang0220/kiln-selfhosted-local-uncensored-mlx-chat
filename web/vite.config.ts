import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = {
  target: "http://127.0.0.1:8787",
  changeOrigin: true,
  timeout: 0,
  proxyTimeout: 0,
};

export default defineConfig({
  plugins: [
    react(),
    {
      name: "favicon-ico",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === "/favicon.ico") {
            res.statusCode = 302;
            res.setHeader("Location", "/favicon.svg");
            res.end();
            return;
          }
          next();
        });
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/auth": api,
      "/chat": api,
      "/conversation": api,
      "/context": api,
      "/health": api,
      "/memory": api,
      "/v1": api,
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          markdown: ["react-markdown", "remark-gfm", "rehype-highlight", "highlight.js"],
          react: ["react", "react-dom", "react-router-dom", "zustand"],
        },
      },
    },
  },
});
