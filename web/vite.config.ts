import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// Mock mode imports the API example responses straight from the repo's test
// fixtures, so the UI and `tests/unit/test_api_fixtures.py` read the same files.
const fixtures = fileURLToPath(new URL("../tests/fixtures/api", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@fixtures": fixtures } },
  server: { port: 5173, fs: { allow: [".."] } },
});
