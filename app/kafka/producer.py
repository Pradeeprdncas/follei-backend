import json
from kafka import KafkaProducer

producer = KafkaProducer(
    bootstrap_servers=['localhost:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def log_event(topic: str, message: dict):
    producer.send(topic, message)
    producer.flush()
