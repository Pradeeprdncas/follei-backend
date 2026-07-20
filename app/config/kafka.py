"""Kafka producer / consumer helpers."""
import json
from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
from app.config.settings import get_settings
from loguru import logger

_settings = get_settings()

_producer: KafkaProducer | None = None


def get_producer() -> KafkaProducer:
    """Lazy singleton Kafka producer."""
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=_settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            retries=3,
            acks="all",
        )
        logger.info("Kafka producer connected")
    return _producer


def ensure_topics():
    """Create required topics if they do not exist."""
    try:
        admin = KafkaAdminClient(
            bootstrap_servers=_settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id="follei-admin",
        )
        existing = admin.list_topics()
        topics_to_create = []
        for t in [_settings.KAFKA_TOPIC_INDEXING, _settings.KAFKA_TOPIC_INDEXING_DLQ, _settings.KAFKA_TOPIC_CHAT]:
            if t not in existing:
                topics_to_create.append(
                    NewTopic(name=t, num_partitions=3, replication_factor=1)
                )
        if topics_to_create:
            admin.create_topics(topics_to_create)
            logger.info(f"Created Kafka topics: {[t.name for t in topics_to_create]}")
        admin.close()
    except Exception as e:
        logger.warning(f"Kafka topic creation skipped (may already exist): {e}")


def get_consumer(topic: str, group_id: str | None = None) -> KafkaConsumer:
    """Build a KafkaConsumer for a given topic."""
    gid = group_id or _settings.KAFKA_CONSUMER_GROUP
    return KafkaConsumer(
        topic,
        bootstrap_servers=_settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=gid,
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        enable_auto_commit=False,
    )
