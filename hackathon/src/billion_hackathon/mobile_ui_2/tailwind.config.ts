import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:       '#282828',
        surface:  '#3c3836',
        border:   '#504945',
        fg:       '#ebdbb2',
        muted:    '#a89984',
        accent:   '#fe8019',
        positive: '#b8bb26',
        negative: '#fb4934',
        warn:     '#fabd2f',
        info:     '#83a598',
      },
    },
  },
  plugins: [],
} satisfies Config
