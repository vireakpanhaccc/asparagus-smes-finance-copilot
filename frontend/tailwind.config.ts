import type { Config } from "tailwindcss";

// Palette from the Overview + Copilot wireframe: light neutrals, one teal accent, amber for alerts.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#1f1f1d", soft: "#3d3d39" },
        teal: { DEFAULT: "#0f6b5a", dark: "#0a4f42", light: "#e8f4f1" },
        warn: { DEFAULT: "#6a4200", bg: "#fbf4e2", border: "#e3cf97", accent: "#c9a24a" },
        danger: { DEFAULT: "#a12a1d", bg: "#fbe9e6" },
        paper: "#f6f6f4",
        side: "#ededea",
        line: "#d6d6d2",
        muted: "#6b6b66",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
