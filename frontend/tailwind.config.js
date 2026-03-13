/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#F7F7F7',
        surface: '#FFFFFF',
        primary: {
          DEFAULT: '#3B82F6',
          foreground: '#FFFFFF',
        },
        success: '#22C55E',
        warning: '#F59E0B',
        alert: '#EF4444',
        neutral: {
          100: '#F1F5F9',
          200: '#E2E8F0',
          500: '#64748B',
          900: '#0F172A',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      backdropBlur: {
        xl: '24px',
      },
      animation: {
        'radar-spin': 'spin 4s linear infinite',
        'pulse-slow': 'ping 3s cubic-bezier(0, 0, 0.2, 1) infinite',
        'pulse-marker': 'pulse-ring 2s ease-out infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        'pulse-ring': {
          '0%': { transform: 'scale(0.8)', opacity: '1' },
          '100%': { transform: 'scale(2)', opacity: '0' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      boxShadow: {
        'glass': '0 8px 32px rgba(0, 0, 0, 0.04)',
        'glass-lg': '0 12px 40px rgba(0, 0, 0, 0.08)',
        'float': '0 4px 20px rgba(0, 0, 0, 0.06)',
      },
    },
  },
  plugins: [],
}
