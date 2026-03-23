/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#0f0f1a",
        sidebar: "#1a1a2e",
        panel: "#16213e",
        border: "#2a2a4a",
        accent: "#6366f1",
        "accent-hover": "#4f46e5",
        "text-primary": "#e2e8f0",
        "text-secondary": "#94a3b8",
        "text-muted": "#64748b",
      },
    },
  },
  plugins: [],
};
