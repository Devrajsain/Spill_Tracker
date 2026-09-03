/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          900: '#061629',
          800: '#0B2545', // Primary Deep Navy
          700: '#133560',
        },
        gov: {
          blue: '#1A3C6E', // Secondary Accent Government Blue
          light: '#F7F8FA', // Light official background
          border: '#E2E5EA', // Thin border gray
          text: '#1A2433', // Primary text
          muted: '#5A6472', // Secondary gray text
          maroon: '#6B1E23', // Subtle highlight maroon
          saffron: '#FF9933', // Tricolor saffron
          green: '#138808', // Tricolor green
        }
      },
      borderRadius: {
        'gov': '4px',
        'gov-lg': '6px',
      },
      fontFamily: {
        sans: ['Inter', 'Source Sans Pro', 'Noto Sans', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
