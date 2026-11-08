import typography from "@tailwindcss/typography";
import plugin from "tailwindcss/plugin";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    ...(process.env.NODE_ENV === "production" ? ["!./src/dev/**"] : []),
    "./channels/*/webui/**/*.{ts,tsx}",
    "./node_modules/streamdown/dist/*.js",
  ],
  theme: {
    container: {
      center: true,
      padding: "1rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      // Text roles own their metrics; reading preferences never change the rem grid.
      fontSize: {
        ui: ["0.8125rem", { lineHeight: "1.25rem", fontWeight: "400" }],
        "ui-label": ["0.75rem", { lineHeight: "1.125rem", fontWeight: "500" }],
        "ui-heading": ["0.8125rem", { lineHeight: "1.25rem", fontWeight: "600" }],
        "ui-body": ["0.875rem", { lineHeight: "1.25rem", fontWeight: "400" }],
        "control-label": ["0.875rem", { lineHeight: "1.25rem", fontWeight: "500" }],
        caption: ["0.75rem", { lineHeight: "1.125rem", fontWeight: "400" }],
        title: ["1.25rem", { lineHeight: "1.75rem", fontWeight: "600" }],
        reading: ["var(--text-reading-size)", { lineHeight: "var(--cjk-line-height)", fontWeight: "400" }],
        "reading-small": ["calc(var(--text-reading-size) * 0.875)", { lineHeight: "var(--cjk-line-height)", fontWeight: "400" }],
        code: ["var(--text-code-size)", { lineHeight: "1.6", fontWeight: "400" }],
        "code-dense": ["var(--text-code-dense-size)", { lineHeight: "1.6", fontWeight: "400" }],
        composer: ["var(--text-composer-size)", { lineHeight: "1.5", fontWeight: "400" }],
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          '"Noto Sans"',
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          "sans-serif",
          '"Apple Color Emoji"',
          '"Segoe UI Emoji"',
        ],
        mono: [
          '"JetBrains Mono"',
          '"SFMono-Regular"',
          '"SF Mono"',
          '"Fira Code"',
          '"Cascadia Code"',
          '"Source Code Pro"',
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        mark: "var(--radius-mark)",
        compact: "var(--radius-compact)",
        control: "var(--radius-control)",
        floating: "var(--radius-floating)",
        panel: "var(--radius-panel)",
        modal: "var(--radius-modal)",
        prominent: "var(--radius-prominent)",
      },
      colors: {
        "content-link": {
          DEFAULT: "var(--content-link)",
          hover: "var(--content-link-hover)",
        },
        background: "hsl(var(--cirno-background))",
        foreground: "hsl(var(--cirno-foreground))",
        card: {
          DEFAULT: "hsl(var(--cirno-card))",
          foreground: "hsl(var(--cirno-card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--cirno-popover))",
          foreground: "hsl(var(--cirno-popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--cirno-primary))",
          foreground: "hsl(var(--cirno-primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--cirno-secondary))",
          foreground: "hsl(var(--cirno-secondary-foreground))",
        },
        muted: {

          foreground: "hsl(var(--cirno-muted-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--cirno-destructive))",
          foreground: "hsl(var(--cirno-destructive-foreground))",
        },
        "diff-added": {
          DEFAULT: "var(--diff-added)",
          foreground: "var(--diff-added-foreground)",
        },
        "diff-deleted": {
          DEFAULT: "var(--diff-deleted)",
          foreground: "var(--diff-deleted-foreground)",
        },
        border: "hsl(var(--cirno-border))",
        input: "hsl(var(--cirno-input))",
        ring: "hsl(var(--cirno-ring))",
        sidebar: {
          DEFAULT: "hsl(var(--cirno-sidebar))",
          foreground: "hsl(var(--cirno-sidebar-foreground))",
          content: "hsl(var(--cirno-sidebar-content))",
          "muted-foreground": "hsl(var(--cirno-sidebar-muted-foreground))",
          selected: "hsl(var(--cirno-sidebar-selected))",
          accent: "hsl(var(--cirno-sidebar-accent))",
          "accent-foreground": "hsl(var(--cirno-sidebar-accent-foreground))",
          border: "hsl(var(--cirno-sidebar-border))",
        },
        settings: {
          canvas: "hsl(var(--cirno-settings-canvas))",
          surface: "hsl(var(--cirno-settings-surface))",
        },
      },
      keyframes: {
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
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [
    typography,
    plugin(({ addVariant, addUtilities }) => {
      addUtilities({ ".rounded-full": { cornerShape: "round" } });
      // Revealing controls on emulated hover can consume the first Safari
      // tap. Keep these sidebar hover effects on hover-capable pointers.
      addVariant("media-hover", "@media (hover: hover)");
    }),
  ],
};
