/**
 * Unified Chart Theme - Based on FOMO Design Screenshots
 * Consistent styling across all charts in the application
 */

// Primary color palette - teal/cyan dominant
export const chartColors = {
  // Primary line/area colors
  primary: '#00C9A7',       // Main teal
  primaryLight: '#4ADEC7',
  primaryGradientStart: 'rgba(0, 201, 167, 0.4)',
  primaryGradientEnd: 'rgba(0, 201, 167, 0.02)',
  
  // Secondary colors for comparison charts
  secondary: '#8B5CF6',     // Purple for second line
  secondaryLight: '#A78BFA',
  
  // Positive/Negative indicators
  positive: '#00C9A7',      // Teal green
  positiveLight: '#4ADEC7',
  negative: '#FF6B8A',      // Soft red/pink
  negativeLight: '#FF8FA5',
  
  // Neutral/Grid colors
  grid: 'rgba(0, 0, 0, 0.04)',
  axis: '#9CA3AF',
  text: '#6B7280',
  textDark: '#374151',
  
  // Chart backgrounds
  background: 'rgba(255, 255, 255, 0.95)',
  tooltipBg: 'rgba(15, 23, 42, 0.95)',
};

// Chart dimensions
export const chartDimensions = {
  height: {
    small: 120,
    medium: 200,
    large: 280,
    xlarge: 350,
  },
  barRadius: [6, 6, 0, 0],
  lineWidth: 2.5,
  dotRadius: 4,
  activeDotRadius: 6,
};

// Common axis configuration
export const axisConfig = {
  tick: {
    fontSize: 11,
    fill: chartColors.axis,
    fontWeight: 500,
    fontFamily: "'Gilroy', -apple-system, sans-serif",
  },
  stroke: chartColors.grid,
  tickLine: false,
  axisLine: false,
};

// Tooltip styles
export const tooltipStyles = {
  wrapper: {
    background: chartColors.tooltipBg,
    backdropFilter: 'blur(20px)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderRadius: '14px',
    padding: '12px 16px',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.25)',
  },
  label: {
    color: 'rgba(255, 255, 255, 0.7)',
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: '8px',
  },
  value: {
    color: '#fff',
    fontSize: '14px',
    fontWeight: 700,
  },
  valuePositive: {
    color: chartColors.positive,
  },
  valueNegative: {
    color: chartColors.negative,
  },
};

// Gradient definitions for Area charts
export const gradientDefs = {
  primaryArea: {
    id: 'primaryAreaGradient',
    colors: [
      { offset: '0%', color: chartColors.primary, opacity: 0.4 },
      { offset: '100%', color: chartColors.primary, opacity: 0.02 },
    ],
  },
  positiveBar: {
    id: 'positiveBarGradient',
    colors: [
      { offset: '0%', color: chartColors.positive, opacity: 1 },
      { offset: '100%', color: chartColors.positiveLight, opacity: 0.8 },
    ],
  },
  negativeBar: {
    id: 'negativeBarGradient',
    colors: [
      { offset: '0%', color: chartColors.negative, opacity: 1 },
      { offset: '100%', color: chartColors.negativeLight, opacity: 0.8 },
    ],
  },
};

// Time period selector options
export const timePeriods = {
  short: ['1H', '4H', '24H'],
  medium: ['24H', '7D', '30D'],
  long: ['7D', '30D', '90D', '1Y', 'ALL'],
};

// Format functions
export const formatters = {
  currency: (value) => {
    if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
    if (Math.abs(value) >= 1e3) return `$${(value / 1e3).toFixed(1)}K`;
    return `$${value.toFixed(2)}`;
  },
  percent: (value) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`,
  shortNumber: (value) => {
    if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
    if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(0)}K`;
    return value.toFixed(0);
  },
};

export default {
  chartColors,
  chartDimensions,
  axisConfig,
  tooltipStyles,
  gradientDefs,
  timePeriods,
  formatters,
};
