# file: app/cache.py

import redis
import json
import logging
import os

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
redis_client = redis.Redis(host=REDIS_HOST, 
                           port=REDIS_PORT, 
                           db=0, 
                           decode_responses=True)

def get_cache(key : str):
    try:
        value = redis_client.get(key)
        if value:
            logger.info(
                "cache_hit",
                extra={"service": "gateway", "cache_key": key}
            )
            return json.loads(value)
        logger.info(
            "cache_miss",
            extra={"service": "gateway", "cache_key": key}
        )
        return None
    except redis.exceptions.RedisError as e:
        logger.warning(
            "get_cache_error",
            extra={"service": "gateway", "cache_key": key, "error": str(e)}
        )
        return None
    
def set_cache(key : str, value, ttl: int = 60):
    try:
        redis_client.setex(key, ttl, json.dumps(value))
        logger.info(
            "cache_set",
            extra={"service": "gateway", "cache_key": key, "ttl": ttl}
        )
    except redis.exceptions.RedisError as e:
        logger.warning(
            "set_cache_error",
            extra={"service": "gateway", "cache_key": key, "error": str(e)}
        )

def delete_cache(key : str):
    try:
        redis_client.delete(key)
        logger.info(
            "cache_delete",
            extra={"service": "gateway", "cache_key": key}
        )
    except redis.exceptions.RedisError as e:
        logger.warning(
            "delete_cache_error",
            extra={"service": "gateway", "cache_key": key, "error": str(e)}
        )

def push_event(queue_name : str, data : dict):
    try:
        redis_client.lpush(queue_name, json.dumps(data))
        logger.info(
            "event_pushed",
            extra={"service": "gateway", "queue_name": queue_name, "event_id": data.get("event_id")}
        )
    except redis.exceptions.RedisError as e:
        logger.warning(
            "push_event_error",
            extra={"service": "gateway", "queue_name": queue_name, "error": str(e)}
        )

def get_queue_length(queue_name : str):
    try:
        length = redis_client.llen(queue_name)
        return length
    except Exception:
        return -1;