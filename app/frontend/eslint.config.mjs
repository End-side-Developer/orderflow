import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  ...nextVitals,
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  {
    rules: {
      // React 19's `react-hooks/set-state-in-effect` flags the standard
      // "set loading state, kick off async fetch, set data on resolve" pattern
      // used widely across this app (page-level fetch effects, Why panel,
      // Judgment Decision panel, page-summary obligation extractor). The
      // pattern is intentional and idiomatic for client-fetched dashboards.
      // Re-enable only if/when these views move to Suspense + RSC.
      "react-hooks/set-state-in-effect": "off",
    },
  },
];

export default config;
