# Intelligence Layer modules
from .topic_extractor import extract_topics
from .topic_momentum import TopicRepository, TopicMomentumEngine, ensure_topic_indexes
from .anomaly_engine import AnomalyRepository, AnomalyEngine
from .signal_engine import (
    SignalRepository, 
    CrossChannelSignalEngine, 
    CrossChannelSignalService,
    ensure_signal_indexes
)
from .cache_layer import (
    FeedCacheRepository,
    TopicMomentumCacheRepository,
    AnomalyCacheRepository,
    ensure_cache_indexes
)
from .alert_engine import (
    AlertEngineV2,
    Alert,
    AlertRepository,
    AlertPreferencesRepository,
    AlertPreferencesService,
    AlertCooldownManager,
    AlertEventBus,
    AlertCore,
    WebAlertChannel,
    TelegramAlertChannel,
    build_anomaly_alert,
    build_cross_channel_alert,
    build_channel_event_alert,
    build_digest_alert,
    ensure_alert_v2_indexes,
    ensure_alert_indexes,
    MAX_ALERTS_PER_HOUR,
    MAX_ALERTS_PER_DAY,
    PRIORITY
)

__all__ = [
    'extract_topics',
    'TopicRepository',
    'TopicMomentumEngine',
    'ensure_topic_indexes',
    'AnomalyRepository',
    'AnomalyEngine',
    'SignalRepository',
    'CrossChannelSignalEngine',
    'CrossChannelSignalService',
    'ensure_signal_indexes',
    'FeedCacheRepository',
    'TopicMomentumCacheRepository',
    'AnomalyCacheRepository',
    'ensure_cache_indexes',
    'AlertEngineV2',
    'Alert',
    'AlertRepository',
    'AlertPreferencesRepository',
    'AlertPreferencesService',
    'AlertCooldownManager',
    'AlertEventBus',
    'AlertCore',
    'WebAlertChannel',
    'TelegramAlertChannel',
    'build_anomaly_alert',
    'build_cross_channel_alert',
    'build_channel_event_alert',
    'build_digest_alert',
    'ensure_alert_v2_indexes',
    'ensure_alert_indexes',
    'MAX_ALERTS_PER_HOUR',
    'MAX_ALERTS_PER_DAY',
    'PRIORITY'
]
