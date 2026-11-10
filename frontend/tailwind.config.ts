import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#030814",
          900: "#060e1f",
          850: "#0a1529",
          800: "#0e1c35",
          700: "#152747",
          600: "#1e355e",
        },
        accent: { DEFAULT: "#22d3ee", soft: "#67e8f9", teal: "#2dd4bf" },
        ink: { DEFAULT: "#e6f1ff", muted: "#94a8c6", faint: "#5f7495" },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "-apple-system", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(34,211,238,0.25), 0 8px 30px -12px rgba(34,211,238,0.35)",
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 10px 30px -15px rgba(0,0,0,0.6)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
        pulseDot: { "0%,100%": { opacity: "0.3" }, "50%": { opacity: "1" } },
      },
      animation: { "fade-in": "fade-in .25s ease-out both", "pulse-dot": "pulseDot 1.2s ease-in-out infinite" },
    },
  },
  plugins: [],
} satisfies Config;
