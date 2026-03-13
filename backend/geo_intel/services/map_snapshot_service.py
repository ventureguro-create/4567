"""
Map Snapshot Service - Generate static map images for Telegram
Uses OpenStreetMap static tiles
"""
import logging
from typing import Optional
import math

logger = logging.getLogger(__name__)

# OpenStreetMap tile server
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

# Alternative: use a static map service
# For production, consider using Mapbox or Google Static Maps API


def generate_osm_url(lat: float, lng: float, zoom: int = 15) -> str:
    """Generate OpenStreetMap URL for location"""
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map={zoom}/{lat}/{lng}"


def generate_static_map_url(
    center_lat: float,
    center_lng: float,
    markers: list = None,
    zoom: int = 15,
    width: int = 600,
    height: int = 400
) -> str:
    """
    Generate static map URL using free services
    
    For production, use one of:
    - Mapbox Static API (free tier available)
    - Google Static Maps
    - MapTiler
    """
    
    # Option 1: OpenStreetMap link (not an image, but useful)
    osm_url = f"https://www.openstreetmap.org/?mlat={center_lat}&mlon={center_lng}#map={zoom}/{center_lat}/{center_lng}"
    
    # Option 2: Geoapify (free tier: 3000 req/day)
    # Requires API key, but has generous free tier
    # geoapify_url = f"https://maps.geoapify.com/v1/staticmap?style=osm-bright&width={width}&height={height}&center=lonlat:{center_lng},{center_lat}&zoom={zoom}&apiKey=YOUR_KEY"
    
    # Option 3: Use a self-hosted tile renderer
    # For now, return OSM link
    return osm_url


def generate_event_map_url(
    user_lat: float,
    user_lng: float,
    event_lat: float,
    event_lng: float,
    event_type: str = "virus"
) -> str:
    """Generate map URL showing user and event positions"""
    
    # Calculate center point between user and event
    center_lat = (user_lat + event_lat) / 2
    center_lng = (user_lng + event_lng) / 2
    
    # Calculate appropriate zoom based on distance
    from ..utils.geo_distance import haversine_distance
    distance = haversine_distance(user_lat, user_lng, event_lat, event_lng)
    
    if distance < 200:
        zoom = 17
    elif distance < 500:
        zoom = 16
    elif distance < 1000:
        zoom = 15
    elif distance < 2000:
        zoom = 14
    else:
        zoom = 13
    
    return generate_static_map_url(center_lat, center_lng, zoom=zoom)


def generate_google_maps_url(lat: float, lng: float) -> str:
    """Generate Google Maps URL for navigation"""
    return f"https://www.google.com/maps?q={lat},{lng}"


def generate_route_url(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float
) -> str:
    """Generate Google Maps route URL"""
    return f"https://www.google.com/maps/dir/{from_lat},{from_lng}/{to_lat},{to_lng}"


class MapSnapshotService:
    """Service for generating map snapshots"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
    
    def get_event_map_url(
        self,
        user_lat: float,
        user_lng: float,
        event_lat: float,
        event_lng: float,
        event_type: str = "virus"
    ) -> str:
        """Get map URL for event alert"""
        return generate_event_map_url(
            user_lat, user_lng,
            event_lat, event_lng,
            event_type
        )
    
    def get_location_url(self, lat: float, lng: float) -> str:
        """Get map URL for single location"""
        return generate_osm_url(lat, lng)
    
    def get_route_url(
        self,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float
    ) -> str:
        """Get route URL"""
        return generate_route_url(from_lat, from_lng, to_lat, to_lng)
    
    def get_google_maps_url(self, lat: float, lng: float) -> str:
        """Get Google Maps URL"""
        return generate_google_maps_url(lat, lng)
