"""Wait until Kafka can answer a metadata request, not merely open a port."""
from __future__ import annotations

import argparse
import time

from kafka import KafkaAdminClient
from kafka.errors import KafkaError


def wait_for_kafka(timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        client = None
        try:
            client = KafkaAdminClient(
                bootstrap_servers="127.0.0.1:9092",
                client_id="follei-startup-check",
                request_timeout_ms=3000,
                api_version_auto_timeout_ms=3000,
            )
            client.list_topics()
            return
        except (KafkaError, OSError) as exc:
            last_error = exc
            time.sleep(1)
        finally:
            if client is not None:
                client.close()
    detail = type(last_error).__name__ if last_error else "unknown error"
    raise RuntimeError(f"Kafka was not ready within {timeout:g} seconds ({detail})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    wait_for_kafka(args.timeout)
    print("kafka_status=ready")
