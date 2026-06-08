import paho.mqtt.client as mqtt
import json
import time
import random
import datetime

import os
from dotenv import load_dotenv

load_dotenv()

MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = "sinergi/iiot"

# Warehouse gateway → node mappings
BASE_GATEWAYS = {
    "GW-IKEA-JKT-01": {
        "env_nodes": ["ENV-IKEA-JKT-001", "ENV-IKEA-JKT-002"],
        "cam_nodes": ["CAM-IKEA-JKT-001"],
    },
    "GW-IKEA-SBY-01": {
        "env_nodes": ["ENV-IKEA-SBY-001"],
        "cam_nodes": ["CAM-IKEA-SBY-001"],
    },
    "GW-INDO-BDG-01": {
        "env_nodes": ["ENV-INDO-BDG-001", "ENV-INDO-BDG-002"],
        "cam_nodes": ["CAM-INDO-BDG-001"],
    },
    "GW-INDO-MDN-01": {
        "env_nodes": ["ENV-INDO-MDN-001"],
        "cam_nodes": ["CAM-INDO-MDN-001"],
    },
}

GATEWAYS = {}
try:
    auth_file_path = os.path.join(os.path.dirname(__file__), '..', 'nextjs_iiot', 'data', 'auth.json')
    if os.path.exists(auth_file_path):
        with open(auth_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        devices = data.get('devices', [])
        # Map up to 4 devices
        for i, (old_gw_id, nodes) in enumerate(BASE_GATEWAYS.items()):
            if i < len(devices):
                new_gw_id = devices[i].get('sn')
                GATEWAYS[new_gw_id] = nodes
            else:
                GATEWAYS[old_gw_id] = nodes
    else:
        GATEWAYS = BASE_GATEWAYS
except Exception as e:
    print(f"Error mapping gateways: {e}")
    GATEWAYS = BASE_GATEWAYS

# Room areas for density calculation (m²)
ROOM_AREAS = {
    "CAM-IKEA-JKT-001": 500.0,
    "CAM-IKEA-SBY-001": 300.0,
    "CAM-INDO-BDG-001": 400.0,
    "CAM-INDO-MDN-001": 250.0,
}


def get_local_timestamp(gateway_id: str):
    """
    Menghasilkan timestamp sesuai dengan zona waktu Gateway.
    - JKT (Jakarta), SBY (Surabaya), BDG (Bandung), MDN (Medan) berada di WIB (UTC+7).
    - Jika ada lokasi di Bali/Makassar (WITA) bisa diset +8, atau Papua (WIT) +9.
    """
    offset_hours = 7  # Default WIB
    if "-WITA-" in gateway_id:
        offset_hours = 8
    elif "-WIT-" in gateway_id:
        offset_hours = 9
        
    tz = datetime.timezone(datetime.timedelta(hours=offset_hours))
    return datetime.datetime.now(tz).isoformat()

def generate_env_payload(gateway_id: str):
    """Generate realistic warehouse environmental sensor data."""
    return {
        "type": "environmental",
        "timestamp": get_local_timestamp(gateway_id),
        "temperature": round(random.uniform(22.0, 38.0), 1),
        "humidity": round(random.uniform(40.0, 85.0), 1),
        "pm25": round(random.uniform(5.0, 80.0), 1),
        "pm10": round(random.uniform(10.0, 120.0), 1),
        "co": round(random.uniform(200.0, 5000.0), 1),
        "no2": round(random.uniform(10.0, 100.0), 1),
        "so2": round(random.uniform(5.0, 60.0), 1),
        "o3": round(random.uniform(20.0, 150.0), 1),
    }


def generate_vision_payload(gateway_id: str, room_area: float):
    """Generate dummy AI Vision detection data."""
    person_count = random.randint(0, 25)
    density = round(person_count / room_area, 4) if room_area > 0 else 0
    return {
        "type": "ai_vision",
        "timestamp": get_local_timestamp(gateway_id),
        "person_count": person_count,
        "density": density,
    }


# Initialize MQTT Client
try:
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    else:
        client = mqtt.Client()
except AttributeError:
    client = mqtt.Client()

print(f"[SIM] SINERGI IIoT Warehouse Simulator (MQTT Mode)")
print(f"   MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
print(f"   Topic Prefix: {MQTT_TOPIC_PREFIX}")
print(f"   Gateways: {len(GATEWAYS)}")
print(f"   Env nodes: {sum(len(g['env_nodes']) for g in GATEWAYS.values())}")
print(f"   Vision nodes: {sum(len(g['cam_nodes']) for g in GATEWAYS.values())}")
print()

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
except Exception as e:
    print(f"[ERROR] Failed to connect to MQTT Broker: {e}")
    exit(1)

try:
    cycle = 0
    while True:
        cycle += 1
        # Pick a random gateway
        gateway_id = random.choice(list(GATEWAYS.keys()))
        gateway = GATEWAYS[gateway_id]

        # 70% chance: publish environmental data
        if random.random() < 0.7 and gateway["env_nodes"]:
            node_id = random.choice(gateway["env_nodes"])
            payload = generate_env_payload(gateway_id)
            topic = f"{MQTT_TOPIC_PREFIX}/{gateway_id}/{node_id}"
            
            try:
                client.publish(topic, json.dumps(payload))
                print(f"[ENV] {gateway_id}/{node_id}: T={payload['temperature']}°C H={payload['humidity']}% Time={payload['timestamp']}")
            except Exception as e:
                print(f"[ERROR] Failed to send ENV data: {e}")
        else:
            # 30% chance: publish AI Vision data
            if gateway["cam_nodes"]:
                node_id = random.choice(gateway["cam_nodes"])
                room_area = ROOM_AREAS.get(node_id, 100.0)
                payload = generate_vision_payload(gateway_id, room_area)
                topic = f"{MQTT_TOPIC_PREFIX}/{gateway_id}/{node_id}"
                
                try:
                    client.publish(topic, json.dumps(payload))
                    print(f"[CAM] {gateway_id}/{node_id}: persons={payload['person_count']} Time={payload['timestamp']}")
                except Exception as e:
                    print(f"[ERROR] Failed to send CAM data: {e}")

        # Sleep 1.5-3 seconds between messages
        time.sleep(random.uniform(1.5, 3.0))

except KeyboardInterrupt:
    print("\n[STOP] Simulator stopped.")
finally:
    client.loop_stop()
    client.disconnect()
