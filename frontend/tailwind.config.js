/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Design.md color palette
        background: "#F7F8FA",
        card: "#FFFFFF",
        text: {
          primary: "#111827",
          secondary: "#6B7280",
        },
        primary: {
          DEFAULT: "#1F4FD8",
          foreground: "#FFFFFF",
        },
        success: {
          DEFAULT: "#16A34A",
          light: "#DCFCE7",
          dark: "#166534",
        },
        warning: {
          DEFAULT: "#D97706",
          light: "#FEF3C7",
          dark: "#B45309",
        },
        critical: {
          DEFAULT: "#DC2626",
          light: "#FEE2E2",
          dark: "#B91C1C",
        },
        neutral: {
          DEFAULT: "#6B7280",
          light: "#F3F4F6",
          dark: "#4B5563",
        },
        border: "#E5E7EB",
        input: "#E5E7EB",
        ring: "#1F4FD8",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      fontSize: {
        "kpi": ["28px", { lineHeight: "1.2", fontWeight: "600", "font-variant-numeric": "tabular-nums" }],
        "kpi-sm": ["24px", { lineHeight: "1.2", fontWeight: "600", "font-variant-numeric": "tabular-nums" }],
        "body": ["14px", { lineHeight: "1.5" }],
        "table-meta": ["12px", { lineHeight: "1.5" }],
      },
      spacing: {
        "18": "4.5rem",
        "88": "22rem",
      },
      borderRadius: {
        "card": "12px",
        "button": "8px",
      },
      boxShadow: {
        "card": "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
        "card-hover": "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
      },
      animation: {
        "fade-in": "fadeIn 150ms ease-out",
        "slide-up": "slideUp 200ms ease-out",
        "slide-down": "slideDown 200ms ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideDown: {
          "0%": { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
}