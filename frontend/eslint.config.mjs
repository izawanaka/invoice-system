import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Aplikasi ini sengaja berupa client-rendered SPA tanpa library fetching
      // (SWR/React Query) -- lihat 05_web_platform_plan.md. Pola standar
      // "setLoading(true) lalu fetch di useEffect" pada tiap halaman (dashboard,
      // po, bap, invoices) dan di auth-context/badan-usaha-context akan selalu
      // kena aturan baru react-hooks v7 ini meski ini pola data-fetching yang
      // wajar untuk skala proyek ini. Diturunkan jadi warning, bukan dimatikan
      // total, supaya tetap terlihat kalau dipakai secara tidak sengaja di
      // tempat lain.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
