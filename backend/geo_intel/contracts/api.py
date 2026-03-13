"""
Geo Intel API Response Contracts
"""
from pydantic import BaseModel
from typing import List, Optional, Any
from .types import GeoEvent, RadarChannel

class GeoMapResponse(BaseModel):
    ok: bool = True
    items: List[dict] = []
    total: int = 0

class GeoTopResponse(BaseModel):
    ok: bool = True
    items: List[dict] = []

class GeoSummaryResponse(BaseModel):
    ok: bool = True
    summary: str = ""
    stats: dict = {}

class RadarChannelsResponse(BaseModel):
    ok: bool = True
    items: List[RadarChannel] = []
    total: int = 0

class GeoStatsResponse(BaseModel):
    ok: bool = True
    totalEvents: int = 0
    totalChannels: int = 0
    topEventTypes: List[dict] = []
    recentActivity: List[dict] = []
