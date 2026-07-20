from app.workers.indexing_consumer import failure_destination
from app.config.settings import get_settings


def test_failed_indexing_is_requeued_before_attempt_limit():
    status, topic = failure_destination(2, 3)

    assert status == "retrying"
    assert topic == get_settings().KAFKA_TOPIC_INDEXING


def test_failed_indexing_is_dead_lettered_at_attempt_limit():
    status, topic = failure_destination(3, 3)

    assert status == "dead_lettered"
    assert topic == get_settings().KAFKA_TOPIC_INDEXING_DLQ
