import os
import json
import time
import logging
import threading

import redis
from pymongo import MongoClient
from dotenv import load_dotenv
from redis.commands.json.path import Path
import json
import logging


# 1. Load environment variables
load_dotenv()

# 2. Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 3. Read Redis configuration from environment or use defaults
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# 4. Read MongoDB configuration from environment or use defaults
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB = os.getenv("MONGO_DB", "conserver")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "vcon")


logger = logging.getLogger(__name__)

def scan_and_sync_redis_to_mongo(redis_client, mongo_collection):
    """
    Scans the Redis keyspace for keys starting with 'vcon:'
    and inserts/updates them in the given MongoDB collection.
    This version uses RedisJSON for handling JSON data in Redis.
    """
    logger.info("Starting one-time scan of keys 'vcon:*' using RedisJSON...")
    cursor = 0
    while True:
        cursor, keys = redis_client.scan(cursor=cursor, match="vcon:*", count=100)
        for key in keys:
            key_str = key.decode("utf-8")
            try:
                # Fetch the value as JSON from Redis
                value = redis_client.json().get(key_str, Path.root_path())
                logger.info(f"Read value from REDIS: {value}")
                logger.info("Type of value: " + str(type(value)))
                if value is not None:
                    # Upsert the document by using the Redis key as the _id
                    mongo_collection.replace_one(
                        {"_id": key_str},
                        value,
                        upsert=True
                    )
                    logger.info(f"Synchronized Redis key '{key_str}' with MongoDB.")
                else:
                    logger.warning(f"Redis key '{key_str}' has no JSON value.")
            except Exception as e:
                logger.error(f"Error reading or syncing key '{key_str}' - {str(e)}")

        if cursor == 0:
            # Completed the full scan
            break

    logger.info("Finished scanning all 'vcon:*' keys.")

def listen_for_redis_keyspace_events(redis_client, mongo_collection, redis_db=0):
    """
    Subscribes to Redis keyspace notifications for events on keys that match 'vcon:*'.
    Whenever a relevant key is created/updated, it is fetched and MongoDB is updated in real time.
    """
    pubsub = redis_client.pubsub()
    channel_pattern = f"__keyspace@{redis_db}__:vcon:*"
    pubsub.psubscribe(channel_pattern)
    logger.info(f"Subscribed to keyspace events on pattern '{channel_pattern}'")

    for message in pubsub.listen():
        if message["type"] == "pmessage":
            data = message["data"]
            # Look for 'set', 'hset', 'json.set', etc. as events
            if data in (b"set", b"hset", b"json.set"):
                channel = message["channel"].decode("utf-8")
                # Example channel: "__keyspace@0__:vcon:123"
                key_name = channel.split(":", 1)[1]

                try:
                    value = redis_client.json().get(key_name, Path.root_path())
                    mongo_collection.replace_one(
                        {"_id": key_name},
                        value,
                        upsert=True
                    )
                    logger.info(f"[Keyspace Event] Updated MongoDB for '{key_name}'")
                except Exception as e:
                    logger.error(f"Error handling key '{key_name}' event - {str(e)}")


def main():
    # 1. Connect to Redis
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

    # 2. Connect to MongoDB
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[MONGO_DB]
    vcon_collection = db[MONGO_COLLECTION]

    # 3. Do an initial scan of existing keys
    scan_and_sync_redis_to_mongo(redis_client, vcon_collection)

    # 4. (Optional) Listen for new updates
    #    This will block the calling thread, so run it in a separate thread if needed
    listener_thread = threading.Thread(
        target=listen_for_redis_keyspace_events,
        args=(redis_client, vcon_collection, REDIS_DB),
        daemon=True
    )
    listener_thread.start()

    # Keep the main thread alive so the listener keeps running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
