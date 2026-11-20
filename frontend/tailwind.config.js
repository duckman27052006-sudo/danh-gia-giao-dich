/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /* "ink" now means the light Aero surfaces (page, cards, inputs) */
        ink: {
          950: "#f2fbff",
          900: "#ffffff",
          850: "#fbfeff",
          800: "#f5fcff",
          700: "#e6f7ff",
          600: "#d3eefa",
        },
        /* dark teal-greens: readable as text on glass, still "mint" in hue */
        mint: {
          200: "#0a5f47",
          300: "#0b7557",
          400: "#0e8a63",
          500: "#12a473",
          600: "#0f8a61",
          700: "#0b6b4b",
        },
        amber: {
          400: "#a75f06",
          500: "#c47110",
        },
        coral: {
          400: "#b93d1e",
          500: "#ef5b34",
        },
        sky: {
          300: "#38bdf8",
          400: "#00a8e8",
          500: "#0284c7",
        },
        azure: {
          400: "#0369a1",
          500: "#0284c7",
        },
        /* inverted slate ramp = readable secondary text on light glass */
        slate: {
          100: "#04384d",
          200: "#0a4560",
          300: "#14546c",
          400: "#1b5e77",
          500: "#2f7288",
          600: "#3d7e95",
          700: "#4f8ea6",
          800: "#e8f6fb",
          900: "#f4fbff",
        },
      },
      fontFamily: {
        sans: ['"Segoe UI"', "Frutiger", '"Trebuchet MS"', '"Be Vietnam Pro"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(0, 168, 232, 0.25), 0 12px 40px -12px rgba(0, 168, 232, 0.35)",
        panel: "0 24px 60px -30px rgba(0, 70, 110, 0.55)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
        "scan-line": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(400%)" },
        },
        "spin-slow": {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.45s cubic-bezier(0.2, 0.7, 0.3, 1) both",
        "fade-in": "fade-in 0.3s ease both",
        shimmer: "shimmer 1.6s linear infinite",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
        "scan-line": "scan-line 3.2s linear infinite",
        "spin-slow": "spin-slow 18s linear infinite",
      },
    },
  },
  plugins: [],
};
