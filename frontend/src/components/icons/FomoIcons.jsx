/**
 * FOMO Custom Icons
 * 
 * Единая коллекция SVG иконок для всего проекта
 * Стиль: минималистичный, монохромный с акцентами
 * Размер по умолчанию: 20x20
 */

import React from 'react';

// Base wrapper для всех иконок
const IconWrapper = ({ children, size = 20, className = '', color = 'currentColor' }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    style={{ color }}
  >
    {children}
  </svg>
);

// ============================================================
// BACKER TYPES
// ============================================================

/** 💰 Fund - Stack of coins */
export const IconFund = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="12" cy="18" r="4" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="12" cy="14" r="4" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="12" cy="10" r="4" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <path d="M12 8V6M12 6L14 8M12 6L10 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </IconWrapper>
);

/** 🏗️ Project - Building blocks */
export const IconProject = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <rect x="3" y="14" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="1.5" />
    <rect x="8.5" y="3" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="1.5" />
    <path d="M12 10V14" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 2" />
  </IconWrapper>
);

/** 🏛️ DAO - Columns/Temple */
export const IconDAO = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 3L3 8V10H21V8L12 3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <rect x="5" y="10" width="2" height="8" stroke="currentColor" strokeWidth="1.5" />
    <rect x="11" y="10" width="2" height="8" stroke="currentColor" strokeWidth="1.5" />
    <rect x="17" y="10" width="2" height="8" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 18H21V20H3V18Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </IconWrapper>
);

/** 🌐 Ecosystem - Connected nodes */
export const IconEcosystem = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="4" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="19" cy="16" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="5" cy="16" r="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M12 9V6M14.5 13.5L17.5 15M9.5 13.5L6.5 15" stroke="currentColor" strokeWidth="1.5" />
  </IconWrapper>
);

/** 🏢 Company - Office building */
export const IconCompany = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <rect x="4" y="4" width="16" height="17" rx="1" stroke="currentColor" strokeWidth="1.5" />
    <rect x="7" y="7" width="3" height="3" stroke="currentColor" strokeWidth="1.5" />
    <rect x="14" y="7" width="3" height="3" stroke="currentColor" strokeWidth="1.5" />
    <rect x="7" y="13" width="3" height="3" stroke="currentColor" strokeWidth="1.5" />
    <rect x="14" y="13" width="3" height="3" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10 21V18H14V21" stroke="currentColor" strokeWidth="1.5" />
  </IconWrapper>
);

// ============================================================
// FILTER CATEGORIES (from Backers page)
// ============================================================

/** VC Funds - briefcase with chart */
export const IconVCFund = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <rect x="2" y="7" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M8 7V5C8 3.89543 8.89543 3 10 3H14C15.1046 3 16 3.89543 16 5V7" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 12L10 15L14 11L17 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </IconWrapper>
);

/** Influencers - person with signal */
export const IconInfluencer = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="9" cy="7" r="4" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 21V19C3 16.7909 4.79086 15 7 15H11C13.2091 15 15 16.7909 15 19V21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M17 8C18.5 8 19 9 19 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M19 6C21.5 6 22.5 8 22.5 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </IconWrapper>
);

/** NFT Projects - art frame */
export const IconNFT = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 15L8 10L12 14L16 10L21 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.5" />
  </IconWrapper>
);

/** Media Partners - newspaper/broadcast */
export const IconMedia = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 8H12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7 12H17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7 16H17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <rect x="14" y="7" width="3" height="3" stroke="currentColor" strokeWidth="1.5" />
  </IconWrapper>
);

// ============================================================
// PATTERN DETECTION
// ============================================================

/** ❤️ Like Farm - heart with nodes */
export const IconLikeFarm = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 20L4.5 12.5C2.5 10.5 2.5 7 4.5 5C6.5 3 10 3 12 5C14 3 17.5 3 19.5 5C21.5 7 21.5 10.5 19.5 12.5L12 20Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <circle cx="8" cy="9" r="1" fill="currentColor" />
    <circle cx="16" cy="9" r="1" fill="currentColor" />
    <circle cx="12" cy="13" r="1" fill="currentColor" />
    <path d="M8 9L12 13L16 9" stroke="currentColor" strokeWidth="1" strokeDasharray="2 1" />
  </IconWrapper>
);

/** 📈 Spike Pump - chart with spike */
export const IconSpikePump = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M3 20L7 16L11 18L15 8L21 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M15 4H21V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M3 20H21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </IconWrapper>
);

/** 🔗 Overlap Farm - connected chains */
export const IconOverlapFarm = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="6" cy="6" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="18" cy="6" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="6" cy="18" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="18" cy="18" r="3" stroke="currentColor" strokeWidth="1.5" />
    <path d="M9 6H15M6 9V15M18 9V15M9 18H15" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="2" stroke="currentColor" strokeWidth="1.5" fill="none" />
  </IconWrapper>
);

// ============================================================
// CLUSTERS & SIGNALS
// ============================================================

/** Cluster - grouped nodes */
export const IconCluster = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 2" />
    <circle cx="8" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="15" cy="9" r="2" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="14" cy="15" r="2.5" stroke="currentColor" strokeWidth="1.5" fill="none" />
    <circle cx="9" cy="15" r="1.5" stroke="currentColor" strokeWidth="1.5" fill="none" />
  </IconWrapper>
);

/** Attention - eye with focus */
export const IconAttention = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M2 12C2 12 5 5 12 5C19 5 22 12 22 12C22 12 19 19 12 19C5 19 2 12 2 12Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
  </IconWrapper>
);

/** Alt Season - multiple charts rising */
export const IconAltSeason = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M4 18L4 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <path d="M8 18L8 11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <path d="M12 18L12 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <path d="M16 18L16 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <path d="M20 18L20 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    <path d="M2 20H22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M2 4L22 4" stroke="currentColor" strokeWidth="1" strokeDasharray="2 2" />
  </IconWrapper>
);

// ============================================================
// LEADERBOARD & RANKINGS
// ============================================================

/** Trophy - for leaderboard */
export const IconTrophy = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M8 21H16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M12 17V21" stroke="currentColor" strokeWidth="1.5" />
    <path d="M17 4H19C20.1046 4 21 4.89543 21 6V8C21 9.65685 19.6569 11 18 11H17" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 4H5C3.89543 4 3 4.89543 3 6V8C3 9.65685 4.34315 11 6 11H7" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 3H17V11C17 14.3137 14.3137 17 12 17C9.68629 17 7 14.3137 7 11V3Z" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10 8H14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </IconWrapper>
);

/** Medal - rank badge */
export const IconMedal = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="12" cy="9" r="6" stroke="currentColor" strokeWidth="1.5" />
    <path d="M12 6V12L15 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M8 15L6 21L12 18L18 21L16 15" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </IconWrapper>
);

// ============================================================
// STRATEGY & SIMULATION
// ============================================================

/** Strategy - chess knight */
export const IconStrategy = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M9 22H15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7 22V19C7 17.8954 7.89543 17 9 17H15C16.1046 17 17 17.8954 17 19V22" stroke="currentColor" strokeWidth="1.5" />
    <path d="M8 17C8 17 7 13 8 10C9 7 12 4 12 4C12 4 10 6 11 8C12 10 14 10 16 8C14 12 13 13 12 17" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <circle cx="10" cy="8" r="1" fill="currentColor" />
  </IconWrapper>
);

/** Simulation - play with gears */
export const IconSimulation = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M8 5.5V8L10 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="16" cy="16" r="5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M16 13.5V16L18 17.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M12 10L14 12" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 1" />
  </IconWrapper>
);

// ============================================================
// LIFECYCLE & STATUS
// ============================================================

/** Lifecycle - circular arrows */
export const IconLifecycle = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 3C16.9706 3 21 7.02944 21 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M21 12C21 16.9706 16.9706 21 12 21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M12 21C7.02944 21 3 16.9706 3 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M3 12C3 7.02944 7.02944 3 12 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M19 9L21 12L18 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M5 15L3 12L6 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </IconWrapper>
);

/** Narratives - book/story icon */
export const IconNarratives = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M4 19.5A2.5 2.5 0 016.5 17H20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M6.5 2H20V22H6.5A2.5 2.5 0 014 19.5V4.5A2.5 2.5 0 016.5 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M8 7H16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M8 11H14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </IconWrapper>
);

/** Status - pulse line */
export const IconPulse = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M2 12H6L8 8L10 16L12 10L14 14L16 12H22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </IconWrapper>
);

// ============================================================
// MISC / COMMON
// ============================================================

/** Brain - AI/Intelligence */
export const IconBrain = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 4C8.68629 4 6 6.68629 6 10C6 11.8638 6.7835 13.5372 8.03553 14.7071C9.28756 15.877 10 17.5504 10 19.4142V20H14V19.4142C14 17.5504 14.7124 15.877 15.9645 14.7071C17.2165 13.5372 18 11.8638 18 10C18 6.68629 15.3137 4 12 4Z" stroke="currentColor" strokeWidth="1.5" />
    <path d="M9 10C9 10 10 11 12 11C14 11 15 10 15 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M10 20V22M14 20V22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M10 8H14" stroke="currentColor" strokeWidth="1" strokeDasharray="1 1" />
  </IconWrapper>
);

/** Network - connected dots */
export const IconNetwork = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="5" cy="6" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="4" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="19" cy="6" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="6" cy="18" r="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="18" cy="18" r="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 6L10 10M14 10L17 6M9 14L7 17M15 14L17 17M12 7V9" stroke="currentColor" strokeWidth="1.5" />
  </IconWrapper>
);

/** Radar - scan circle */
export const IconRadar = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="1" stroke="currentColor" strokeWidth="1.5" />
    <path d="M12 12L18 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="15" cy="9" r="1.5" fill="currentColor" />
  </IconWrapper>
);

/** Signal - wifi-like waves */
export const IconSignal = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 18C12.5523 18 13 17.5523 13 17C13 16.4477 12.5523 16 12 16C11.4477 16 11 16.4477 11 17C11 17.5523 11.4477 18 12 18Z" fill="currentColor" />
    <path d="M8.46447 14.4645C9.40215 13.5268 10.6739 13 12 13C13.3261 13 14.5979 13.5268 15.5355 14.4645" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M5.63604 11.636C7.32387 9.94821 9.61305 9 12 9C14.3869 9 16.6761 9.94821 18.364 11.636" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M3 8.80761C5.37258 6.43503 8.58172 5.09326 12 5.09326C15.4183 5.09326 18.6274 6.43503 21 8.80761" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </IconWrapper>
);

// ============================================================
// NARRATIVE STATES
// ============================================================

/** Seeding - plant sprout */
export const IconSeeding = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 22V14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M12 14C12 14 8 12 8 8C8 4 12 2 12 2C12 2 16 4 16 8C16 12 12 14 12 14Z" stroke="currentColor" strokeWidth="1.5" />
    <path d="M8 22H16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M10 18L12 14L14 18" stroke="currentColor" strokeWidth="1" strokeDasharray="2 1" />
  </IconWrapper>
);

/** Ignition - rocket launching */
export const IconIgnition = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 2C12 2 7 7 7 12C7 14.5 8.5 17 12 17C15.5 17 17 14.5 17 12C17 7 12 2 12 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M9 17L7 22M15 17L17 22M12 17V20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="12" cy="10" r="2" stroke="currentColor" strokeWidth="1.5" />
  </IconWrapper>
);

/** Expansion - expanding circles */
export const IconExpansion = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" />
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" strokeDasharray="5 5" />
    <path d="M12 3V1M12 23V21M21 12H23M1 12H3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </IconWrapper>
);

/** Target/Crosshair */
export const IconTarget = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
    <path d="M12 2V6M12 18V22M2 12H6M18 12H22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </IconWrapper>
);

/** Fire/Hot trend */
export const IconFire = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 22C16.4183 22 20 18.4183 20 14C20 11.5 18.5 9 16.5 7.5C16.5 9 15.5 10.5 14 11C14 8 12 5 9 3C9 6 7 8 5.5 10C4.5 11.5 4 13.5 4 14C4 18.4183 7.58172 22 12 22Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M12 22C13.6569 22 15 19.5 15 17C15 15 14 14 12 13C10 14 9 15 9 17C9 19.5 10.3431 22 12 22Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </IconWrapper>
);

/** Decay/Down trend */
export const IconDecay = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M21 7L13 15L9 11L3 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M21 7V13M21 7H15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M3 20H21" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </IconWrapper>
);

/** Warning - triangle alert */
export const IconWarning = ({ size = 20, className = '', color }) => (
  <IconWrapper size={size} className={className} color={color}>
    <path d="M12 3L2 20H22L12 3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M12 9V13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="12" cy="16" r="1" fill="currentColor" />
  </IconWrapper>
);

// Export all icons as a map for easy lookup
export const FomoIcons = {
  // Backer types
  fund: IconFund,
  project: IconProject,
  dao: IconDAO,
  ecosystem: IconEcosystem,
  company: IconCompany,
  // Filter categories
  vcfund: IconVCFund,
  influencer: IconInfluencer,
  nft: IconNFT,
  media: IconMedia,
  // Patterns
  likeFarm: IconLikeFarm,
  spikePump: IconSpikePump,
  overlapFarm: IconOverlapFarm,
  // Clusters & Signals
  cluster: IconCluster,
  attention: IconAttention,
  altSeason: IconAltSeason,
  // Rankings
  trophy: IconTrophy,
  medal: IconMedal,
  // Strategy
  strategy: IconStrategy,
  simulation: IconSimulation,
  // Lifecycle
  lifecycle: IconLifecycle,
  narratives: IconNarratives,
  pulse: IconPulse,
  // Common
  brain: IconBrain,
  network: IconNetwork,
  radar: IconRadar,
  signal: IconSignal,
  // Narrative states
  seeding: IconSeeding,
  ignition: IconIgnition,
  expansion: IconExpansion,
  target: IconTarget,
  fire: IconFire,
  decay: IconDecay,
  warning: IconWarning,
};

export default FomoIcons;
