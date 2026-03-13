"""
Cell Encoder Service
Uses geohash for cell-based location matching
Enables fast proximity lookups without calculating distance for every user
"""
import logging
from typing import List, Tuple, Set
import math

logger = logging.getLogger(__name__)

# Geohash character set
GEOHASH_CHARS = "0123456789bcdefghjkmnpqrstuvwxyz"

# Precision levels (characters -> approximate cell size)
# 4 chars ~ 39km x 19.5km
# 5 chars ~ 4.9km x 4.9km  
# 6 chars ~ 1.2km x 0.6km  <- Good for 1km radius
# 7 chars ~ 153m x 153m    <- Good for 500m radius
# 8 chars ~ 38m x 19m

RADIUS_TO_PRECISION = {
    500: 7,    # 153m cells
    1000: 6,   # 1.2km cells
    2000: 6,   # 1.2km cells
    5000: 5,   # 4.9km cells
}


def encode_geohash(lat: float, lng: float, precision: int = 6) -> str:
    """
    Encode lat/lng to geohash string
    
    Args:
        lat: Latitude (-90 to 90)
        lng: Longitude (-180 to 180)
        precision: Number of characters (default 6 ~ 1.2km)
    
    Returns:
        Geohash string
    """
    lat_range = (-90.0, 90.0)
    lng_range = (-180.0, 180.0)
    
    geohash = []
    bits = 0
    bit_count = 0
    even_bit = True
    
    while len(geohash) < precision:
        if even_bit:
            mid = (lng_range[0] + lng_range[1]) / 2
            if lng >= mid:
                bits = (bits << 1) | 1
                lng_range = (mid, lng_range[1])
            else:
                bits = bits << 1
                lng_range = (lng_range[0], mid)
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                bits = (bits << 1) | 1
                lat_range = (mid, lat_range[1])
            else:
                bits = bits << 1
                lat_range = (lat_range[0], mid)
        
        even_bit = not even_bit
        bit_count += 1
        
        if bit_count == 5:
            geohash.append(GEOHASH_CHARS[bits])
            bits = 0
            bit_count = 0
    
    return ''.join(geohash)


def decode_geohash(geohash: str) -> Tuple[float, float]:
    """
    Decode geohash to lat/lng center point
    
    Returns:
        (lat, lng) tuple
    """
    lat_range = (-90.0, 90.0)
    lng_range = (-180.0, 180.0)
    even_bit = True
    
    for char in geohash:
        idx = GEOHASH_CHARS.index(char.lower())
        for i in range(4, -1, -1):
            bit = (idx >> i) & 1
            if even_bit:
                mid = (lng_range[0] + lng_range[1]) / 2
                if bit:
                    lng_range = (mid, lng_range[1])
                else:
                    lng_range = (lng_range[0], mid)
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if bit:
                    lat_range = (mid, lat_range[1])
                else:
                    lat_range = (lat_range[0], mid)
            even_bit = not even_bit
    
    lat = (lat_range[0] + lat_range[1]) / 2
    lng = (lng_range[0] + lng_range[1]) / 2
    
    return (lat, lng)


def get_neighbors(geohash: str) -> List[str]:
    """
    Get all 8 neighboring cells plus the cell itself
    
    Returns:
        List of 9 geohash strings (center + 8 neighbors)
    """
    lat, lng = decode_geohash(geohash)
    precision = len(geohash)
    
    # Calculate approximate cell size
    lat_err = 90.0 / (2 ** (precision * 5 // 2))
    lng_err = 180.0 / (2 ** ((precision * 5 + 1) // 2))
    
    neighbors = set()
    neighbors.add(geohash)
    
    # 8 directions
    offsets = [
        (-lat_err, -lng_err), (-lat_err, 0), (-lat_err, lng_err),
        (0, -lng_err), (0, lng_err),
        (lat_err, -lng_err), (lat_err, 0), (lat_err, lng_err),
    ]
    
    for dlat, dlng in offsets:
        new_lat = lat + dlat * 2
        new_lng = lng + dlng * 2
        
        # Clamp to valid range
        new_lat = max(-90, min(90, new_lat))
        new_lng = max(-180, min(180, new_lng))
        
        neighbor_hash = encode_geohash(new_lat, new_lng, precision)
        neighbors.add(neighbor_hash)
    
    return list(neighbors)


def get_cells_for_radius(lat: float, lng: float, radius_meters: int) -> dict:
    """
    Get cell and neighbors for a given location and radius
    
    Args:
        lat: Latitude
        lng: Longitude
        radius_meters: Radius in meters (500, 1000, 2000, 5000)
    
    Returns:
        dict with cell info
    """
    # Get appropriate precision for radius
    precision = RADIUS_TO_PRECISION.get(radius_meters, 6)
    
    # For larger radii, we might need more neighbors
    cells_needed = 1
    if radius_meters >= 2000:
        cells_needed = 2  # Need 2 layers of neighbors
    
    cell = encode_geohash(lat, lng, precision)
    neighbors = get_neighbors(cell)
    
    # For larger radii, get neighbors of neighbors
    if cells_needed > 1:
        extended = set(neighbors)
        for n in neighbors:
            extended.update(get_neighbors(n))
        neighbors = list(extended)
    
    return {
        "cell": cell,
        "neighbors": neighbors,
        "precision": precision,
        "radiusBucket": f"{radius_meters}m"
    }


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate distance between two points in meters
    
    Uses Haversine formula for accurate Earth surface distance
    """
    R = 6371000  # Earth radius in meters
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def round_location(lat: float, lng: float, precision_meters: int = 100) -> Tuple[float, float]:
    """
    Round location for privacy (coarse precision)
    
    Args:
        lat, lng: Original coordinates
        precision_meters: Rounding precision (default 100m)
    
    Returns:
        Rounded (lat, lng)
    """
    # Approximate degrees per meter at equator
    # 1 degree latitude ~ 111,000 meters
    # 1 degree longitude varies by latitude
    
    lat_precision = precision_meters / 111000
    lng_precision = precision_meters / (111000 * math.cos(math.radians(lat)))
    
    rounded_lat = round(lat / lat_precision) * lat_precision
    rounded_lng = round(lng / lng_precision) * lng_precision
    
    return (round(rounded_lat, 6), round(rounded_lng, 6))


# Export main functions
__all__ = [
    'encode_geohash',
    'decode_geohash', 
    'get_neighbors',
    'get_cells_for_radius',
    'haversine_distance',
    'round_location',
    'RADIUS_TO_PRECISION'
]
