/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Deep Winter palette colours for the UI
        palette: {
          black: '#000000',
          white: '#FFFFFF',
          emerald: '#006B3C',
          'royal-blue': '#4169E1',
          red: '#CC0000',
          burgundy: '#800020',
          plum: '#580F41',
          fuchsia: '#FF0090',
          cobalt: '#0047AB',
          charcoal: '#36454F',
          navy: '#000080',
          teal: '#008080',
          mahogany: '#3C1F1F',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Playfair Display', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
}
