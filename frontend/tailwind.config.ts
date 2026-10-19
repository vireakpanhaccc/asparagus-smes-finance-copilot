import type { Config } from "tailwindcss";

// Colour tokens from my-data-handoff.md: one blue for actions and money in, red for money out
// and alerts, amber for "needs your OK". Never use the WeBank logo; colours only.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          blue: "#1D4F9F", // primary: buttons, links, active nav, chart line, money in
          blue700: "#163D7C", // hover, active nav text
          blue50: "#EAF0FA", // selected/info backgrounds, "File"/"By you" badges
          blue100: "#A9BEE0", // outline buttons, chip borders
          red: "#E1251B", // brand dot, shortfall alert button, shortfall marker
          red700: "#C41E16", // money out, Delete links, red text (passes contrast)
          red800: "#A3170F", // text on red-50
          red50: "#FDECEA", // alert / blocked backgrounds
          red200: "#F6C3BF", // alert borders
          amber: "#8A5A00", // "Needs your OK", held, overdue (text)
          amber50: "#FFF4DD", // same, background
          ink: "#14213D", // body text
          muted: "#5B6478", // secondary text
          sub: "#3A4660", // tertiary text, nav items
          line: "#DCE2EC", // borders
          line2: "#EEF1F6", // table row dividers, Bank badge background
          field: "#C5CEDD", // input borders
          panel: "#F5F7FB", // sidebar, table header, info lines, input fill
        },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Noto Sans Khmer", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
