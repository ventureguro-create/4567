"""
Movement Intelligence Engine
Detects clusters, movement patterns, and trajectories
Makes the map smart - not just static points
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from .cell_encoder import haversine_distance, encode_geohash
import secrets

logger = logging.getLogger(__name__)

# Cluster parameters
CLUSTER_RADIUS_METERS = 300
CLUSTER_TIME_WINDOW_MINUTES = 30
MIN_SIGNALS_FOR_CLUSTER = 2

# Movement parameters
MOVEMENT_RADIUS_METERS = 1000
MOVEMENT_TIME_WINDOW_MINUTES = 60


class MovementEngine:
    """Detects movement patterns, clusters, and trajectories"""
    
    def __init__(self, db):
        self.db = db
        self.signals = db.geo_signals
        self.clusters = db.geo_clusters
        self.movements = db.geo_movements
    
    async def find_nearby_signals(
        self,
        lat: float,
        lng: float,
        radius_meters: int,
        time_window_minutes: int,
        exclude_id: str = None
    ) -> List[Dict[str, Any]]:
        """Find signals within radius and time window"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        
        # Get all recent signals
        query = {
            "createdAt": {"$gte": cutoff},
            "status": {"$ne": "dismissed"}
        }
        
        if exclude_id:
            query["signalId"] = {"$ne": exclude_id}
        
        signals = await self.signals.find(query, {"_id": 0}).to_list(500)
        
        # Filter by distance
        nearby = []
        for signal in signals:
            sig_lat = signal.get("lat")
            sig_lng = signal.get("lng")
            if sig_lat and sig_lng:
                distance = haversine_distance(lat, lng, sig_lat, sig_lng)
                if distance <= radius_meters:
                    signal["distance"] = round(distance)
                    nearby.append(signal)
        
        return nearby
    
    async def detect_cluster(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Detect if signal belongs to a cluster
        Cluster = multiple signals in same area within time window
        """
        lat = signal.get("lat")
        lng = signal.get("lng")
        signal_id = signal.get("signalId")
        
        if not lat or not lng:
            return None
        
        # Find nearby signals
        nearby = await self.find_nearby_signals(
            lat, lng,
            CLUSTER_RADIUS_METERS,
            CLUSTER_TIME_WINDOW_MINUTES,
            exclude_id=signal_id
        )
        
        if len(nearby) < MIN_SIGNALS_FOR_CLUSTER - 1:
            return None
        
        # Check if any nearby signal already has a cluster
        existing_cluster_id = None
        for sig in nearby:
            if sig.get("clusterId"):
                existing_cluster_id = sig.get("clusterId")
                break
        
        if existing_cluster_id:
            # Add to existing cluster
            cluster = await self.clusters.find_one({"clusterId": existing_cluster_id})
            if cluster:
                await self._add_signal_to_cluster(cluster, signal)
                return cluster
        
        # Create new cluster
        cluster = await self._create_cluster(signal, nearby)
        return cluster
    
    async def _create_cluster(
        self,
        signal: Dict[str, Any],
        nearby_signals: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create a new cluster"""
        now = datetime.now(timezone.utc)
        cluster_id = f"cluster_{secrets.token_hex(8)}"
        
        # Calculate centroid
        all_signals = [signal] + nearby_signals
        centroid_lat = sum(s.get("lat", 0) for s in all_signals) / len(all_signals)
        centroid_lng = sum(s.get("lng", 0) for s in all_signals) / len(all_signals)
        
        # Get dominant event type
        types = [s.get("eventType") for s in all_signals]
        dominant_type = max(set(types), key=types.count) if types else "unknown"
        
        cluster = {
            "clusterId": cluster_id,
            "centroidLat": round(centroid_lat, 6),
            "centroidLng": round(centroid_lng, 6),
            "cell": encode_geohash(centroid_lat, centroid_lng, 6),
            "eventType": dominant_type,
            "signalIds": [s.get("signalId") for s in all_signals],
            "signalCount": len(all_signals),
            "startTime": min(s.get("createdAt", now) for s in all_signals),
            "lastUpdate": now,
            "status": "active",
            "createdAt": now
        }
        
        await self.clusters.insert_one(cluster)
        
        # Update signals with cluster ID
        for sig in all_signals:
            await self.signals.update_one(
                {"signalId": sig.get("signalId")},
                {"$set": {"clusterId": cluster_id}}
            )
        
        logger.info(f"Created cluster {cluster_id} with {len(all_signals)} signals")
        
        return cluster
    
    async def _add_signal_to_cluster(
        self,
        cluster: Dict[str, Any],
        signal: Dict[str, Any]
    ) -> None:
        """Add signal to existing cluster and update centroid"""
        cluster_id = cluster.get("clusterId")
        signal_id = signal.get("signalId")
        
        # Update cluster
        await self.clusters.update_one(
            {"clusterId": cluster_id},
            {
                "$push": {"signalIds": signal_id},
                "$inc": {"signalCount": 1},
                "$set": {"lastUpdate": datetime.now(timezone.utc)}
            }
        )
        
        # Update signal
        await self.signals.update_one(
            {"signalId": signal_id},
            {"$set": {"clusterId": cluster_id}}
        )
        
        logger.info(f"Added signal {signal_id} to cluster {cluster_id}")
    
    async def detect_movement(self, cluster: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Detect if cluster is part of a movement pattern
        Movement = cluster centroid shifted significantly
        """
        cluster_id = cluster.get("clusterId")
        cluster_lat = cluster.get("centroidLat")
        cluster_lng = cluster.get("centroidLng")
        
        if not cluster_lat or not cluster_lng:
            return None
        
        # Find recent clusters of same type nearby
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=MOVEMENT_TIME_WINDOW_MINUTES)
        
        previous_clusters = await self.clusters.find({
            "eventType": cluster.get("eventType"),
            "createdAt": {"$lt": cluster.get("createdAt"), "$gte": cutoff},
            "clusterId": {"$ne": cluster_id}
        }).sort("createdAt", -1).limit(5).to_list(5)
        
        # Check for movement
        for prev in previous_clusters:
            prev_lat = prev.get("centroidLat")
            prev_lng = prev.get("centroidLng")
            
            if prev_lat and prev_lng:
                distance = haversine_distance(cluster_lat, cluster_lng, prev_lat, prev_lng)
                
                if distance <= MOVEMENT_RADIUS_METERS and distance > CLUSTER_RADIUS_METERS:
                    # This is a movement!
                    movement = await self._create_movement(prev, cluster, distance)
                    return movement
        
        return None
    
    async def _create_movement(
        self,
        from_cluster: Dict[str, Any],
        to_cluster: Dict[str, Any],
        distance: float
    ) -> Dict[str, Any]:
        """Create a movement record"""
        now = datetime.now(timezone.utc)
        movement_id = f"movement_{secrets.token_hex(8)}"
        
        # Calculate direction (simple: N/S/E/W)
        lat_diff = to_cluster.get("centroidLat", 0) - from_cluster.get("centroidLat", 0)
        lng_diff = to_cluster.get("centroidLng", 0) - from_cluster.get("centroidLng", 0)
        
        if abs(lat_diff) > abs(lng_diff):
            direction = "north" if lat_diff > 0 else "south"
        else:
            direction = "east" if lng_diff > 0 else "west"
        
        # Calculate speed (m/min)
        time_diff = (to_cluster.get("createdAt", now) - from_cluster.get("createdAt", now)).total_seconds() / 60
        speed = distance / max(time_diff, 1)
        
        movement = {
            "movementId": movement_id,
            "eventType": to_cluster.get("eventType"),
            "fromClusterId": from_cluster.get("clusterId"),
            "toClusterId": to_cluster.get("clusterId"),
            "path": [
                [from_cluster.get("centroidLat"), from_cluster.get("centroidLng")],
                [to_cluster.get("centroidLat"), to_cluster.get("centroidLng")]
            ],
            "distance": round(distance),
            "direction": direction,
            "speed": round(speed, 1),  # m/min
            "startTime": from_cluster.get("createdAt"),
            "endTime": to_cluster.get("createdAt"),
            "createdAt": now
        }
        
        await self.movements.insert_one(movement)
        
        # Update clusters
        await self.clusters.update_one(
            {"clusterId": from_cluster.get("clusterId")},
            {"$set": {"nextClusterId": to_cluster.get("clusterId"), "hasMovement": True}}
        )
        await self.clusters.update_one(
            {"clusterId": to_cluster.get("clusterId")},
            {"$set": {"prevClusterId": from_cluster.get("clusterId"), "hasMovement": True}}
        )
        
        logger.info(f"Detected movement {movement_id}: {direction}, {round(distance)}m")
        
        return movement
    
    async def get_active_clusters(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get active clusters"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        clusters = await self.clusters.find(
            {"lastUpdate": {"$gte": cutoff}, "status": "active"},
            {"_id": 0}
        ).sort("lastUpdate", -1).to_list(100)
        
        return clusters
    
    async def get_recent_movements(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent movements"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        movements = await self.movements.find(
            {"createdAt": {"$gte": cutoff}},
            {"_id": 0}
        ).sort("createdAt", -1).to_list(50)
        
        return movements
    
    async def get_hotspots(self, days: int = 7, min_signals: int = 5) -> List[Dict[str, Any]]:
        """
        Find hotspots - areas with frequent signals
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Aggregate signals by cell
        pipeline = [
            {"$match": {"createdAt": {"$gte": cutoff}}},
            {
                "$group": {
                    "_id": "$cell",
                    "count": {"$sum": 1},
                    "avgLat": {"$avg": "$lat"},
                    "avgLng": {"$avg": "$lng"},
                    "types": {"$push": "$eventType"}
                }
            },
            {"$match": {"count": {"$gte": min_signals}}},
            {"$sort": {"count": -1}},
            {"$limit": 20}
        ]
        
        results = await self.signals.aggregate(pipeline).to_list(20)
        
        hotspots = []
        for r in results:
            types = r.get("types", [])
            dominant_type = max(set(types), key=types.count) if types else "unknown"
            
            hotspots.append({
                "cell": r.get("_id"),
                "lat": round(r.get("avgLat", 0), 6),
                "lng": round(r.get("avgLng", 0), 6),
                "signalCount": r.get("count"),
                "dominantType": dominant_type,
                "frequency": round(r.get("count") / days, 1)  # signals per day
            })
        
        return hotspots
    
    async def process_new_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Full processing pipeline for new signal:
        1. Detect cluster
        2. Detect movement
        3. Update trust score
        """
        result = {
            "signalId": signal.get("signalId"),
            "cluster": None,
            "movement": None
        }
        
        # Detect cluster
        cluster = await self.detect_cluster(signal)
        if cluster:
            result["cluster"] = {
                "clusterId": cluster.get("clusterId"),
                "signalCount": cluster.get("signalCount")
            }
            
            # Detect movement
            movement = await self.detect_movement(cluster)
            if movement:
                result["movement"] = {
                    "movementId": movement.get("movementId"),
                    "direction": movement.get("direction"),
                    "distance": movement.get("distance")
                }
        
        return result


async def ensure_movement_indexes(db):
    """Create indexes for movement intelligence"""
    # Clusters
    await db.geo_clusters.create_index("clusterId", unique=True)
    await db.geo_clusters.create_index("cell")
    await db.geo_clusters.create_index([("lastUpdate", -1)])
    await db.geo_clusters.create_index("eventType")
    
    # Movements
    await db.geo_movements.create_index("movementId", unique=True)
    await db.geo_movements.create_index([("createdAt", -1)])
    await db.geo_movements.create_index("eventType")
    
    logger.info("Movement intelligence indexes created")
