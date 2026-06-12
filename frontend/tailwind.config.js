/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#EEF4FF",
          100: "#D9E6FF",
          200: "#B3CCFF",
          300: "#6699FF",
          400: "#0047FF",
          500: "#0033CC",
          600: "#0028A3",
          700: "#001F7A",
          800: "#0A1240",
          900: "#050A30",
        },
        accent: {
          400: "#00E0FF",
          500: "#00C8E6",
        },
        surface: {
          page: "#F8FAFC",
          card: "#FFFFFF",
        },
      },
      boxShadow: {
        card: "0 1px 3px 0 rgb(5 10 48 / 0.06), 0 1px 2px -1px rgb(5 10 48 / 0.06)",
        glow: "0 0 20px rgb(0 224 255 / 0.15)",
      },
    },
  },
  plugins: [],
};
