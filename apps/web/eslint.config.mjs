import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    files: ["**/*.{js,mjs,ts,tsx}"],
    rules: {
      "no-console": ["error", { allow: ["warn", "error"] }],
      "import/no-anonymous-default-export": "error",
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }
      ],
      "@typescript-eslint/consistent-type-imports": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/purity": "off",
      "react-hooks/exhaustive-deps": "off"
    }
  },
  {
    files: ["**/*.test.mjs", "tests/**/*.mjs", "pages/**/*.test.mjs"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off"
    }
  }
];

export default config;
