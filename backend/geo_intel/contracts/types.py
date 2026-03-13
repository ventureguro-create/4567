"""
Geo Intel Type Contracts
FROZEN after v1.0.0
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

EventType = Literal["virus", "trash"]
GeoPrecision = Literal["exact", "approx", "city", "unknown"]

class GeoPoint(BaseModel):
    lat: float
    lng: float

class GeoSource(BaseModel):
    username: str
    messageId: int
    date: Optional[datetime] = None

class GeoEntity(BaseModel):
    kind: Literal["place", "address", "district", "tag"]
    value: str

class GeoMetrics(BaseModel):
    views: int = 0
    forwards: int = 0
    replies: int = 0

class GeoEvent(BaseModel):
    actorId: str = "anon"
    source: GeoSource
    eventType: EventType = "place"
    title: str
    addressText: str
    location: Optional[GeoPoint] = None
    geoPrecision: GeoPrecision = "unknown"
    evidenceText: str = ""
    entities: List[GeoEntity] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    metrics: GeoMetrics = Field(default_factory=GeoMetrics)
    score: float = 0.0
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

class RadarChannel(BaseModel):
    """Channel added to Radar watchlist"""
    username: str
    title: Optional[str] = None
    avatarUrl: Optional[str] = None
    members: int = 0
    addedAt: Optional[datetime] = None
    lastScanAt: Optional[datetime] = None
    eventsCount: int = 0
    enabled: bool = True
