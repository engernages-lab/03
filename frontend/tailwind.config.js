/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        studio: {
          950: "#07090f",
          900: "#0b0f18",
          850: "#0f1521",
          800: "#141b29",
          700: "#1c2536",
          600: "#27334a",
          500: "#3a4a67",
          400: "#5b6d8c",
          300: "#8b9bb5",
          200: "#b9c5d8",
          100: "#e2e8f2",
        },
        accent: {
          DEFAULT: "#3ddc97",
          soft: "#2bbf81",
          dim: "#1d8a5e",
        },
        key: {
          amber: "#f5a524",
          violet: "#8b5cf6",
          cyan: "#22d3ee",
          rose: "#fb7185",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 12px 32px -12px rgba(0,0,0,0.8)",
        glow: "0 0 0 1px rgba(61,220,151,0.35), 0 0 24px -6px rgba(61,220,151,0.45)",
      },
      keyframes: {
        "pulse-slow": {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "pulse-slow": "pulse-slow 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
