/**
 * Game Icons - High quality SVG icons from game-icons.net
 * Style: Game/Military/Tactical look
 * License: CC-BY 3.0
 */

// Police Car - tactical style
export const PoliceCarIcon = ({ size = 24, color = '#3B82F6', ...props }) => (
  <svg width={size} height={size} viewBox="0 0 512 512" fill={color} {...props}>
    <path d="M120 136c-13.3 0-24 10.7-24 24v16h-8c-13.3 0-24 10.7-24 24v96c0 13.3 10.7 24 24 24h8v8c0 13.3 10.7 24 24 24h32c13.3 0 24-10.7 24-24v-8h160v8c0 13.3 10.7 24 24 24h32c13.3 0 24-10.7 24-24v-8h8c13.3 0 24-10.7 24-24v-96c0-13.3-10.7-24-24-24h-8v-16c0-13.3-10.7-24-24-24H120zm16 40h240v32H136v-32zm-32 64h48v32H104v-32zm256 0h48v32h-48v-32zM184 296h144v24H184v-24z"/>
    <circle cx="136" cy="360" r="32"/>
    <circle cx="376" cy="360" r="32"/>
  </svg>
);

// Skull/Orc - menacing creature
export const SkullOrcIcon = ({ size = 24, color = '#22C55E', ...props }) => (
  <svg width={size} height={size} viewBox="0 0 512 512" fill={color} {...props}>
    <path d="M256 48C141.1 48 48 141.1 48 256c0 63.1 28.1 119.6 72.5 157.8V464h80v-48h111v48h80v-50.2C435.9 375.6 464 319.1 464 256c0-114.9-93.1-208-208-208zm-80 176c17.7 0 32 14.3 32 32s-14.3 32-32 32-32-14.3-32-32 14.3-32 32-32zm160 0c17.7 0 32 14.3 32 32s-14.3 32-32 32-32-14.3-32-32 14.3-32 32-32zm-80 128c-35.3 0-64-14.3-64-32h128c0 17.7-28.7 32-64 32z"/>
    <path d="M224 288h16v48h-16zm48 0h16v48h-16z"/>
  </svg>
);

// Biohazard Symbol
export const BiohazardIcon = ({ size = 24, color = '#22C55E', ...props }) => (
  <svg width={size} height={size} viewBox="0 0 512 512" fill={color} {...props}>
    <path d="M256 48c-27.5 0-53.4 6.6-76.4 18.3 5.7 22.8 9.4 46.6 10.8 70.8 20.8-9.4 43.4-14.6 65.6-14.6s44.8 5.2 65.6 14.6c1.4-24.2 5.1-48 10.8-70.8-23-11.7-48.9-18.3-76.4-18.3zm-144.6 63.4c-35.9 29.2-60.6 71.2-66.8 119.3 22.4 6.3 44.3 15.2 65 26.5 4.7-28.6 17.1-55.4 35.8-77.2-14.5-20.2-26.4-43.1-34-68.6zm289.2 0c-7.6 25.5-19.5 48.4-34 68.6 18.7 21.8 31.1 48.6 35.8 77.2 20.7-11.3 42.6-20.2 65-26.5-6.2-48.1-30.9-90.1-66.8-119.3zM256 192c-70.7 0-128 57.3-128 128 0 23.1 6.1 44.8 16.8 63.5 24-3.6 48.5-5.5 73.2-5.5h76c24.7 0 49.2 1.9 73.2 5.5 10.7-18.7 16.8-40.4 16.8-63.5 0-70.7-57.3-128-128-128zm0 48c44.2 0 80 35.8 80 80s-35.8 80-80 80-80-35.8-80-80 35.8-80 80-80zm-172.6 95.3C53.5 359.4 32 394.4 32 432c0 17.7 14.3 32 32 32h136c-33.8-30.5-54.7-74.8-54.7-123.6 0-1.5.1-3 .1-4.5-22-12.1-42.8-26.5-62-43.6zm345.2 0c-19.2 17.1-40 31.5-62 43.6 0 1.5.1 3 .1 4.5 0 48.8-20.9 93.1-54.7 123.6H448c17.7 0 32-14.3 32-32 0-37.6-21.5-72.6-51.4-96.7z"/>
    <circle cx="256" cy="320" r="32"/>
  </svg>
);

// Toxic Cloud / Acid Rain
export const ToxicCloudIcon = ({ size = 24, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 512 512" fill="none" {...props}>
    <path d="M400 192c0-79.5-64.5-144-144-144-63.2 0-116.9 40.7-136.3 97.3C53.5 152.8 0 211.5 0 284c0 79.5 64.5 144 144 144h240c70.7 0 128-57.3 128-128 0-57.7-38.1-106.4-90.5-122.4C417.7 167.3 416 179.5 400 192z" fill="#8B5CF6"/>
    <g fill="#22C55E" stroke="#22C55E" strokeWidth="8">
      <line x1="144" y1="380" x2="144" y2="440"/>
      <line x1="200" y1="400" x2="200" y2="480"/>
      <line x1="256" y1="380" x2="256" y2="440"/>
      <line x1="312" y1="400" x2="312" y2="480"/>
      <line x1="368" y1="380" x2="368" y2="440"/>
    </g>
  </svg>
);

// Trash with Toxic Waste
export const ToxicTrashIcon = ({ size = 24, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 512 512" fill="none" {...props}>
    <path d="M432 144H80l32 320h288l32-320z" stroke="#3B82F6" strokeWidth="32" fill="none"/>
    <path d="M176 64h160v80H176V64z" stroke="#3B82F6" strokeWidth="24" fill="none"/>
    <line x1="64" y1="144" x2="448" y2="144" stroke="#3B82F6" strokeWidth="32"/>
    <circle cx="256" cy="320" r="48" fill="#22C55E"/>
    <path d="M256 260v30m-25 15l20 10m-20 30l20-10m25 15v-30m25-15l-20-10m20-30l-20 10" stroke="#22C55E" strokeWidth="10"/>
  </svg>
);

// Barricade / Checkpoint
export const BarricadeIcon = ({ size = 24, color = '#F59E0B', ...props }) => (
  <svg width={size} height={size} viewBox="0 0 512 512" fill={color} {...props}>
    <rect x="64" y="224" width="384" height="64" rx="8"/>
    <rect x="96" y="144" width="32" height="224"/>
    <rect x="384" y="144" width="32" height="224"/>
    <circle cx="112" cy="128" r="24"/>
    <circle cx="400" cy="128" r="24"/>
    <g stroke={color} strokeWidth="16">
      <line x1="160" y1="224" x2="192" y2="288"/>
      <line x1="256" y1="224" x2="288" y2="288"/>
      <line x1="352" y1="224" x2="384" y2="288"/>
    </g>
  </svg>
);

// Combined Orc + Trash Icon
export const OrcTrashComboIcon = ({ size = 24, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 512 512" fill="none" {...props}>
    {/* Orc skull on left */}
    <g transform="translate(32, 128)">
      <circle cx="96" cy="96" r="80" fill="#22C55E"/>
      <circle cx="64" cy="80" r="16" fill="#0F172A"/>
      <circle cx="128" cy="80" r="16" fill="#0F172A"/>
      <path d="M60 120 Q96 140 132 120" stroke="#0F172A" strokeWidth="8" fill="none"/>
    </g>
    
    {/* Plus sign */}
    <g transform="translate(224, 200)">
      <line x1="0" y1="32" x2="64" y2="32" stroke="#F59E0B" strokeWidth="12"/>
      <line x1="32" y1="0" x2="32" y2="64" stroke="#F59E0B" strokeWidth="12"/>
    </g>
    
    {/* Trash on right */}
    <g transform="translate(304, 96)">
      <path d="M24 64h128l16 192H8L24 64z" stroke="#3B82F6" strokeWidth="16" fill="none"/>
      <rect x="48" y="32" width="80" height="32" stroke="#3B82F6" strokeWidth="12" fill="none"/>
      <line x1="0" y1="64" x2="176" y2="64" stroke="#3B82F6" strokeWidth="16"/>
    </g>
  </svg>
);

// Fire/Incident
export const FireIcon = ({ size = 24, color = '#EF4444', ...props }) => (
  <svg width={size} height={size} viewBox="0 0 512 512" fill={color} {...props}>
    <path d="M256 32c-17.7 0-32 14.3-32 32v16.6c-48.7 20.2-83.4 67.6-83.4 123.4 0 37.4 15.3 71.2 40 95.6-15.6 19.8-24.6 44.8-24.6 72.4 0 63.5 51.5 115 115 115h85c63.5 0 115-51.5 115-115 0-27.6-9.7-52.9-25.9-72.7 24.4-24.4 39.9-58.1 39.9-95.3 0-55.8-34.7-103.2-83.4-123.4V64c0-17.7-14.3-32-32-32h-13.6zm-32 192c0-35.3 28.7-64 64-64s64 28.7 64 64c0 23.6-12.8 44.2-31.8 55.3-8.4-2.7-17.4-4.3-26.6-4.3h-11.2c-9.2 0-18.2 1.6-26.6 4.3-19-11.1-31.8-31.7-31.8-55.3z"/>
  </svg>
);
