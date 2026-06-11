/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0efff',
          100: '#e1deff',
          200: '#c3bdff',
          300: '#a69eff',
          400: '#8b7cff',
          500: '#6d5df6',
          600: '#5949e2',
          700: '#4638c7',
          800: '#382ca5',
          900: '#302587',
          950: '#1c1557',
        },
        slate: {
          950: '#03050a',
          900: '#070b14',
          850: '#0e1424',
          800: '#131c31',
          750: '#1e2942',
          700: '#2c3a5e',
          600: '#475569',
          500: '#64748b',
          400: '#94a3b8',
          300: '#cbd5e1',
          200: '#e2e8f0',
          100: '#f1f5f9',
        }
      },
      fontFamily: {
        sans: ['Outfit', 'Inter', 'sans-serif'],
      },
      boxShadow: {
        glass: '0 8px 32px 0 rgba(0, 0, 0, 0.5)',
        glow: '0 0 10px rgba(109, 93, 246, 0.12)',
        'glow-emerald': '0 0 10px rgba(16, 185, 129, 0.12)',
      },
      backdropBlur: {
        xs: '2px',
      },
      transitionDuration: {
        '200': '200ms',
      },
      transitionTimingFunction: {
        'ease-out-smooth': 'cubic-bezier(0.16, 1, 0.3, 1)',
      }
    },
  },
  plugins: [],
}
