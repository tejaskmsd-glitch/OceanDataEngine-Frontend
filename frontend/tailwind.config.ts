import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ocean: {
          abyss: "#030710",       // Deepest abyss / charcoal
          deep: "#071220",        // Very dark navy background
          surface: "#0d1d33",     // Subtle card / panel background
          panel: "rgba(10, 24, 44, 0.75)", // Translucent panel
          hover: "rgba(22, 45, 77, 0.6)",
          border: "rgba(255, 255, 255, 0.08)",
          borderLight: "rgba(255, 255, 255, 0.14)",
          teal: {
            DEFAULT: "#15616d",   // Muted, natural desaturated teal
            light: "#268290",
            dark: "#0b3b42",
          },
          blue: {
            DEFAULT: "#1d3f66",   // Muted ocean blue
            light: "#2a578a",
            dark: "#0f233a",
          },
          green: {
            DEFAULT: "#1e6b52",   // Natural kelp / marine flora
            light: "#2a8f6e",
            dark: "#124233",
          },
          sand: "#d4c8b8",        // Seafloor sand / coral warmth
          coral: "#c86d51",       // Muted natural coral
          muted: "#8899a6",       // Muted gray for metadata
          dim: "#536471",         // Dim gray for secondary IDs
          text: "#f0f4f8",        // Soft off-white
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "-apple-system", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
