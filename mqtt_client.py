import paho.mqtt.client as mqtt
import json
from database import SessionLocal
import crud
import asyncio

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC_PATTERN = "sinergi/iiot/+/+"  # sinergi/iiot/{gateway_id}/{node_id}


def on_connect(client, userdata, flags, rc):
    print(f"✅ Connected to MQTT broker (rc={rc})")
    client.subscribe(MQTT_TOPIC_PATTERN)
    print(f"📡 Subscribed to: {MQTT_TOPIC_PATTERN}")


def on_message(client, userdata, msg):
    manager, loop = userdata
    payload_str = msg.payload.decode()

    # Parse topic: sinergi/iiot/{gateway_id}/{node_id}
    parts = msg.topic.split("/")
    if len(parts) != 4:
        print(f"⚠️ Unexpected topic format: {msg.topic}")
        return

    _, _, gateway_id, node_id = parts

    try:
        data = json.loads(payload_str)
        data_type = data.get("type", "environmental")

        db = SessionLocal()
        try:
            if data_type == "environmental":
                crud.save_env_sensor_data(db, gateway_id, node_id, data)
            elif data_type == "ai_vision":
                crud.save_vision_snapshot(db, gateway_id, node_id, data)
            else:
                print(f"⚠️ Unknown data type: {data_type}")
                return
        finally:
            db.close()

        # Broadcast update to WebSocket clients
        if manager and loop:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast_gateway_update(gateway_id), loop
            )

    except Exception as e:
        print(f"❌ Error processing MQTT message: {e}")
        import traceback
        traceback.print_exc()


def start_mqtt_client(manager=None):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    client = mqtt.Client(userdata=(manager, loop))
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    return client
