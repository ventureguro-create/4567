"""
Geo Intel Geocoder Service
Converts addresses/places to lat/lng coordinates
"""
import os
import logging
from typing import Optional, Tuple
import httpx

logger = logging.getLogger(__name__)


class BaseGeocoder:
    """Base geocoder interface"""
    
    async def geocode(self, query: str) -> Optional[Tuple[float, float, str]]:
        """
        Geocode address/place name to coordinates.
        Returns: (lat, lng, precision) or None
        """
        raise NotImplementedError


class GoogleGeocoder(BaseGeocoder):
    """Google Maps Geocoding API"""
    
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
        self.default_city = os.getenv("GEO_DEFAULT_CITY", "Kyiv, Ukraine")
        self.base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    
    async def geocode(self, query: str) -> Optional[Tuple[float, float, str]]:
        if not self.api_key:
            logger.warning("Google Maps API key not configured")
            return None
        
        # Append default city for better results
        full_query = f"{query}, {self.default_city}"
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self.base_url,
                    params={
                        "address": full_query,
                        "key": self.api_key,
                        "language": "uk"  # Ukrainian
                    }
                )
                data = response.json()
            
            if data.get("status") != "OK" or not data.get("results"):
                return None
            
            result = data["results"][0]
            location = result["geometry"]["location"]
            
            # Determine precision
            location_type = result["geometry"].get("location_type", "")
            if location_type in ("ROOFTOP", "RANGE_INTERPOLATED"):
                precision = "exact"
            elif location_type == "GEOMETRIC_CENTER":
                precision = "approx"
            else:
                precision = "city"
            
            return (location["lat"], location["lng"], precision)
            
        except Exception as e:
            logger.error(f"Google geocode error for '{query}': {e}")
            return None


class NominatimGeocoder(BaseGeocoder):
    """OpenStreetMap Nominatim Geocoder (free, no API key)"""
    
    def __init__(self):
        self.default_city = os.getenv("GEO_DEFAULT_CITY", "Kyiv")
        self.base_url = "https://nominatim.openstreetmap.org/search"
        self.user_agent = "GeoIntel/1.0"
    
    async def geocode(self, query: str) -> Optional[Tuple[float, float, str]]:
        full_query = f"{query}, {self.default_city}"
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self.base_url,
                    params={
                        "q": full_query,
                        "format": "json",
                        "limit": 1,
                        "addressdetails": 1
                    },
                    headers={"User-Agent": self.user_agent}
                )
                data = response.json()
            
            if not data:
                return None
            
            result = data[0]
            lat = float(result["lat"])
            lng = float(result["lon"])
            
            # Determine precision based on type
            osm_type = result.get("type", "")
            if osm_type in ("house", "building", "shop", "restaurant"):
                precision = "exact"
            elif osm_type in ("street", "road"):
                precision = "approx"
            else:
                precision = "city"
            
            return (lat, lng, precision)
            
        except Exception as e:
            logger.error(f"Nominatim geocode error for '{query}': {e}")
            return None


def get_geocoder() -> BaseGeocoder:
    """Get appropriate geocoder based on config"""
    if os.getenv("GOOGLE_MAPS_API_KEY"):
        return GoogleGeocoder()
    else:
        logger.info("Using Nominatim geocoder (no Google API key)")
        return NominatimGeocoder()
