/**
 * Signal Types Configuration - Custom PNG Icons
 * Icons created by user, stored in /public/icons/
 */

// PNG Icon component
const PngIcon = ({ src, size = 24, alt = '', ...props }) => (
  <img 
    src={src} 
    alt={alt}
    width={size} 
    height={size} 
    style={{ objectFit: 'contain' }}
    {...props}
  />
);

// Create icon component factory
const createIconComponent = (iconName) => {
  const IconComponent = ({ size = 24, ...props }) => (
    <PngIcon 
      src={`/icons/${iconName}.png`} 
      size={size} 
      alt={iconName}
      {...props}
    />
  );
  IconComponent.displayName = `${iconName}Icon`;
  return IconComponent;
};

// Icon components
export const PoliceIcon = createIconComponent('police');
export const VirusIcon = createIconComponent('virus');
export const WeatherIcon = createIconComponent('weather');
export const TrashIcon = createIconComponent('trash');
export const DangerIcon = createIconComponent('danger');
export const IncidentIcon = createIconComponent('incident');

export const SIGNAL_TYPES = [
  {
    id: 'police',
    iconComponent: PoliceIcon,
    iconPath: '/icons/police.png',
    labelUa: 'Поліція',
    color: '#3B82F6',
    priority: 1,
    isCustomPng: true,
    severity: 0.6,
  },
  {
    id: 'virus',
    iconComponent: VirusIcon,
    iconPath: '/icons/virus.png',
    labelUa: 'Вірус',
    color: '#22C55E',
    priority: 2,
    isCustomPng: true,
    severity: 0.9,
  },
  {
    id: 'weather',
    iconComponent: WeatherIcon,
    iconPath: '/icons/weather.png',
    labelUa: 'Погода',
    color: '#8B5CF6',
    priority: 3,
    isCustomPng: true,
    severity: 0.5,
  },
  {
    id: 'trash',
    iconComponent: TrashIcon,
    iconPath: '/icons/trash.png',
    labelUa: 'Сміття',
    color: '#22C55E',
    priority: 4,
    isCustomPng: true,
    severity: 0.4,
  },
  {
    id: 'danger',
    iconComponent: DangerIcon,
    iconPath: '/icons/danger.png',
    labelUa: 'Небезпека',
    color: '#F59E0B',
    priority: 1,
    isCustomPng: true,
    severity: 0.95,
  },
  {
    id: 'incident',
    iconComponent: IncidentIcon,
    iconPath: '/icons/incident.png',
    labelUa: 'Інцидент',
    color: '#22C55E',
    priority: 2,
    isCustomPng: true,
    severity: 0.85,
  },
];

export function getSignalType(id) {
  return SIGNAL_TYPES.find(t => t.id === id) || SIGNAL_TYPES[0];
}

export function getSignalIcon(id) {
  return getSignalType(id).iconComponent;
}

export function getSignalColor(id) {
  return getSignalType(id).color;
}

export function getSignalSeverity(id) {
  return getSignalType(id).severity || 0.5;
}

export function getSignalIconPath(id) {
  return getSignalType(id).iconPath;
}
