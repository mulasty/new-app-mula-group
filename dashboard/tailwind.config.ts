import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef9f8",
          100: "#d6f0ec",
          600: "#0f766e",
          700: "#115e59",
          900: "#052e2b"
        }
      }
    },
  },
  plugins: [],
};

export default config;
