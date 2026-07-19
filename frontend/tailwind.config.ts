import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "28px",
      screens: { "2xl": "1176px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        paper: "var(--paper)",
        ink: "var(--ink)",
        quiet: "var(--quiet)",
        line: "var(--line)",
        "line-strong": "var(--line-strong)",
        wash: "var(--wash)",
        electric: {
          DEFAULT: "var(--electric)",
          hover: "var(--electric-hover)",
          onink: "var(--electric-on-ink)",
          wash: "var(--electric-wash)",
        },
        danger: "var(--danger)",
      },
      fontFamily: {
        display: ['"Clash Display"', '"DM Sans"', "system-ui", "sans-serif"],
        sans: ['"DM Sans"', "system-ui", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "display-xl": ["clamp(3.5rem, 9vw, 7.5rem)", { lineHeight: "0.95", letterSpacing: "-0.02em", fontWeight: "500" }],
        display: ["4rem", { lineHeight: "1.06", letterSpacing: "-0.02em", fontWeight: "500" }],
        h1: ["2.5rem", { lineHeight: "1.1", letterSpacing: "-0.01em", fontWeight: "500" }],
        h2: ["1.75rem", { lineHeight: "1.21", letterSpacing: "-0.01em", fontWeight: "500" }],
        h3: ["1.25rem", { lineHeight: "1.4", fontWeight: "600" }],
        h4: ["1.0625rem", { lineHeight: "1.41", fontWeight: "600" }],
        body: ["1rem", { lineHeight: "1.625" }],
        small: ["0.875rem", { lineHeight: "1.43" }],
        "mono-data": ["0.8125rem", { lineHeight: "1.54" }],
        "mono-label": ["0.75rem", { lineHeight: "1.33", letterSpacing: "0.06em" }],
      },
      spacing: {
        cell: "14px",
        gutter: "28px",
        "gutter-lg": "56px",
        section: "112px",
      },
      maxWidth: {
        grid: "1176px",
        measure: "62ch",
        "measure-narrow": "34ch",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        ctrl: "4px",
        warm: "8px",
      },
      boxShadow: {
        lift: "0 12px 32px -12px rgba(14, 14, 12, 0.18), 0 2px 6px rgba(14, 14, 12, 0.08)",
      },
      transitionDuration: {
        "120": "120ms",
        "180": "180ms",
        "240": "240ms",
        "320": "320ms",
      },
      transitionTimingFunction: {
        swift: "cubic-bezier(0.22, 1, 0.36, 1)",
        travel: "cubic-bezier(0.65, 0, 0.35, 1)",
        spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
      keyframes: {
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        shimmer: "shimmer 1.6s linear infinite",
        "fade-up": "fade-up 320ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 180ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
