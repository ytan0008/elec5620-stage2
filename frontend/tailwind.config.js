export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        night: '#0d0a24', abyss: '#07051a', dusk: '#1b1442', plum: '#2a1d5c', violet: '#4b2fa8',
        magenta: '#ff4fd8', cyan: '#3ef0ff', lime: '#b8ff5c', sun: '#ffd34d', ember: '#ff8a3d', rose: '#ff6b8b',
        moon: '#f4ecff', mist: '#b9b0e0', fog: '#7d74ad',
      },
      fontFamily: {
        pixel: ['"Pixelify Sans"', 'system-ui', 'sans-serif'],
        arcade: ['"Press Start 2P"', '"Pixelify Sans"', 'monospace'],
        terminal: ['VT323', 'ui-monospace', 'monospace'],
        read: ['"DM Sans"', 'system-ui', 'sans-serif'],
        sans: ['"Pixelify Sans"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
