import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // The API layer receives loosely-typed JSON (LLM output, FastAPI errors)
      // and narrows it at the boundary; typing every adapter point is tracked
      // work, so this stays a warning instead of blocking the build.
      "@typescript-eslint/no-explicit-any": "warn",
      // react-hooks v6 flags the mount-guard / fetch-on-mount pattern used
      // across these pages. It is a warning until the data layer moves to
      // TanStack Query's useQuery (which this project already depends on).
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
