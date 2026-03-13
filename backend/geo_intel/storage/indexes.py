"""
Geo Intel MongoDB Indexes
"""
import logging

logger = logging.getLogger(__name__)

async def ensure_geo_indexes(db):
    """Create all required indexes for geo_intel module"""
    try:
        # tg_geo_events - main events collection
        await db.tg_geo_events.create_index(
            [("actorId", 1), ("dedupeKey", 1)],
            unique=True,
            background=True
        )
        
        await db.tg_geo_events.create_index(
            [("actorId", 1), ("createdAt", -1)],
            background=True
        )
        
        await db.tg_geo_events.create_index(
            [("actorId", 1), ("eventType", 1), ("createdAt", -1)],
            background=True
        )
        
        await db.tg_geo_events.create_index(
            [("source.username", 1), ("source.messageId", 1)],
            background=True
        )
        
        # 2dsphere index for geo queries
        await db.tg_geo_events.create_index(
            [("location", "2dsphere")],
            background=True,
            sparse=True  # Only index docs with location
        )
        
        # tg_radar_channels - channels added to radar
        await db.tg_radar_channels.create_index(
            [("username", 1)],
            unique=True,
            background=True
        )
        
        await db.tg_radar_channels.create_index(
            [("enabled", 1), ("lastScanAt", 1)],
            background=True
        )
        
        logger.info("Geo Intel indexes created successfully")
        
    except Exception as e:
        logger.error(f"Error creating geo indexes: {e}")
