/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#000000",
          accent: "#1d9bf0",
        },
      },
    },
  },
  plugins: [],
};
