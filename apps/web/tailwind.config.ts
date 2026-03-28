import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#1F3864",
          hover: "#162A4D",
          light: "#2E75B6",
          surface: "#E8EFF8",
        },
        success: {
          DEFAULT: "#28A745",
          surface: "#E6F4EA",
        },
        warning: {
          DEFAULT: "#E6A817",
          surface: "#FFF8E1",
        },
        error: {
          DEFAULT: "#DC3545",
          surface: "#FDEDED",
        },
        info: {
          DEFAULT: "#0D6EFD",
          surface: "#E7F1FF",
        },
        neutral: {
          900: "#1A1A1A",
          700: "#404040",
          600: "#666666",
          500: "#888888",
          400: "#AAAAAA",
          200: "#D9D9D9",
          100: "#F2F2F2",
          50: "#F8F8F8",
        },
      },
      fontFamily: {
        sans: ['"Inter"', "-apple-system", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"SF Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        sm: "0 1px 2px rgba(0, 0, 0, 0.06)",
        md: "0 4px 8px rgba(0, 0, 0, 0.08)",
        lg: "0 8px 24px rgba(0, 0, 0, 0.12)",
        xl: "0 16px 48px rgba(0, 0, 0, 0.16)",
        focus: "0 0 0 3px rgba(46, 117, 182, 0.3)",
      },
      borderRadius: {
        sm: "4px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        full: "9999px",
      },
    },
  },
  plugins: [],
} satisfies Config;
