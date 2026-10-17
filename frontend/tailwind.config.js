/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Warm forest stack — readable, not neon-AI.
        canvas: '#07110E',
        surface: '#0C1814',
        'surface-2': '#12211C',
        'surface-3': '#1A2C25',
        line: '#243830',
        ink: '#F2F7F4',
        'ink-muted': '#A7B8B0',
        'ink-faint': '#73857C',
        accent: '#3DCF9A',
        'accent-dim': '#143528',
        // Estimates / secondary — sand, not purple.
        mist: '#C9B8A0',
        'mist-dim': '#2A241C',
        amber: '#E0A84A',
        rose: '#E8898F',
        sky: '#7EB8C9',
        // Keep aliases so existing JSX keeps compiling during the refresh.
        violet: '#C9B8A0',
        'violet-dim': '#2A241C',
      },
      fontFamily: {
        sans: ['"Instrument Sans"', 'Segoe UI', 'system-ui', 'sans-serif'],
        display: ['"Instrument Serif"', 'Georgia', 'serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        lg: '0.625rem',
        xl: '0.75rem',
        '2xl': '1rem',
      },
      boxShadow: {
        panel: '0 1px 0 rgba(255,255,255,0.03) inset, 0 12px 40px rgba(0,0,0,0.28)',
      },
      backgroundImage: {
        atmosphere:
          'radial-gradient(1200px 600px at 12% -10%, rgba(61,207,154,0.10), transparent 55%), radial-gradient(900px 500px at 92% 8%, rgba(201,184,160,0.07), transparent 50%)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-500px 0' },
          '100%': { backgroundPosition: '500px 0' },
        },
        'hero-drift': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'hero-fade': {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'line-draw': {
          '0%': { transform: 'scaleX(0)', opacity: '0.2' },
          '100%': { transform: 'scaleX(1)', opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.35s ease-out',
        shimmer: 'shimmer 1.4s linear infinite',
        'hero-drift': 'hero-drift 9s ease-in-out infinite',
        'hero-fade': 'hero-fade 0.7s ease-out both',
        'line-draw': 'line-draw 1.1s ease-out both',
      },
    },
  },
  plugins: [],
}
