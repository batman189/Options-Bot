/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Terminal dark palette
        base:    "#080c10",
        surface: "#0f1419",
        panel:   "#141c24",
        border:  "#1e2d3d",
        muted:   "#6b7a8d",
        text:    "#e8edf2",
        // Accent
        gold:    "#f0a500",
        "gold-dim": "#8a6000",
        // Status
        profit:  "#00d68f",
        loss:    "#ff4757",
        active:  "#1a6bff",
        // Profile status
        created:  "#6b7a8d",
        training: "#f0a500",
        ready:    "#00d68f",
        paused:   "#6b7a8d",
        error:    "#ff4757",
      },
      fontFamily: {
        sans:  ["'DM Sans'", "system-ui", "sans-serif"],
        mono:  ["'IBM Plex Mono'", "monospace"],
      },
      fontSize: {
        "2xs": "0.65rem",
      },
    },
  },
  plugins: [],
}
