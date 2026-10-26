// ESLint for a React front end in JavaScript, from the dev-setup template
// (dolev2/claude-config, skills/dev-setup/templates/eslint.config.js).
// The rules follow ~/.claude/rules/code-react.md wherever a machine can check them.
//
// Install, in the folder of package.json:
//   npm install -D eslint@10.13.0 @eslint/js@10.0.1 eslint-plugin-react-hooks@7.1.1 \
//     eslint-plugin-react-refresh@0.5.7 globals@17.13.0
// and set the script "lint": "eslint ." (package.json needs "type": "module", as Vite sets it).
//
// Everything above the "--- local ---" line is identical in every repo: dev-setup reports a
// copy whose upper part differs from the template. Change the template, not the copy.
// What is specific to this repo goes into local() at the end.

import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";

export default [
  { ignores: ["dist/", "coverage/"] },
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  js.configs.recommended,
  reactHooks.configs.flat.recommended,
  reactRefresh.configs.vite,
  {
    rules: {
      // An unused import or variable is an error; a leading underscore marks one on purpose.
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      // A warning, not an error: it also flags the common load-on-mount pattern
      // (setLoading inside an effect), and fixing that is a restructure, not a lint fix.
      // Measured on WayOut, 2026-10-26: 25 hits.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  {
    // Tests and build config run in Node, and export no components.
    files: ["**/*.test.{js,jsx}", "**/test/**", "*.config.js"],
    languageOptions: { globals: { ...globals.node, ...globals.vitest } },
    rules: { "react-refresh/only-export-components": "off" },
  },
  ...local(),
];

// --- local ---
// Config objects specific to this repo, for example { ignores: ["src/generated/"] }.
// A function, because its declaration is hoisted above the export.
function local() {
  return [];
}
