import type { Config } from "tailwindcss";

// Palette from the SME Finance Copilot design (teal + ink).
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#0f2a2e", soft: "#1d3d41" },
        teal: { DEFAULT: "#0f6b5a", light: "#e8f4f1" },
        warn: { DEFAULT: "#7a4b00", bg: "#fdf3d8", border: "#ecd48f" },
        danger: { DEFAULT: "#a12a1d", bg: "#fbe9e6" },
        paper: "#f4f6f5",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
