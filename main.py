from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import database
import models
import crud
from mqtt_client import start_mqtt_client
import hmac
import hashlib
import base64
import json
import asyncio
import datetime
from typing import Optional

JWT_SECRET = "liquidglass_secret_token_2026"


# ── JWT Verification ─────────────────────────────────────────────

def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += '=' * pad
    return base64.urlsafe_b64decode(s)


def verify_jwt(token: str):
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        message = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_sig = hmac.new(JWT_SECRET.encode('utf-8'), message, hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload_json = _b64url_decode(payload_b64).decode('utf-8')
        payload = json.loads(payload_json)
        if 'exp' in payload and payload['exp'] < datetime.datetime.utcnow().timestamp():
            return None
        return payload
    except Exception as e:
        print(f"JWT error: {e}")
        return None


# ── RBAC ─────────────────────────────────────────────────────────

import os

def get_accessible_gateways(company_id: str, role: str):
    if role == 'role_admin' or company_id == 'comp_fmipa_ugm':
        return None  # None = all gateways
        
    try:
        auth_file_path = os.path.join(os.path.dirname(__file__), '..', 'nextjs_iiot', 'data', 'auth.json')
        if os.path.exists(auth_file_path):
            with open(auth_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Find devices claimed by this company
            claimed_devices = []
            for device in data.get('devices', []):
                if device.get('company_id') == company_id and device.get('status') == 'active':
                    # The simulator gateways have IDs like "GW-IKEA-JKT-01" or SNs.
                    # Wait, the frontend might be expecting the gateway's ID. 
                    # Does the SN match the gateway ID in the simulator database?
                    claimed_devices.append(device.get('sn'))
                    
            # Fallback to hardcoded just in case they haven't been provisioned yet but exist in legacy simulator
            COMPANY_GATEWAYS = {
                "comp_ikea_id": ["GW-IKEA-JKT-01", "GW-IKEA-SBY-01"],
                "comp_indogrosir": ["GW-INDO-BDG-01", "GW-INDO-MDN-01"],
            }
            legacy_gateways = COMPANY_GATEWAYS.get(company_id, [])
            
            return list(set(claimed_devices + legacy_gateways))
    except Exception as e:
        print(f"Error reading auth.json: {e}")
        
    # Absolute fallback
    COMPANY_GATEWAYS = {
        "comp_ikea_id": ["GW-IKEA-JKT-01", "GW-IKEA-SBY-01"],
        "comp_indogrosir": ["GW-INDO-BDG-01", "GW-INDO-MDN-01"],
    }
    return COMPANY_GATEWAYS.get(company_id, [])



# ── Data Formatting ──────────────────────────────────────────────

def format_env_node(node, env_config, latest_data, hourly_data):
    """Format an environmental node with its sensor data."""
    hourly_trend = []
    sensors = []
    ispu_info = {"value": 0, "label": "Offline", "color": "#6b7280", "status": "baik"}

    if latest_data:
        ispu_info = crud.get_ispu_level(latest_data.ispu)
        ispu_info["value"] = latest_data.ispu

        sensors = [
            {"id": "temperature", "label": "Temperature", "value": latest_data.temperature, "unit": "°C", "threshold": env_config.temp_threshold if env_config else 35, "min": 15, "max": 45},
            {"id": "humidity", "label": "Humidity", "value": latest_data.humidity, "unit": "%", "threshold": env_config.hum_threshold if env_config else 80, "min": 0, "max": 100},
            {"id": "pm25", "label": "PM2.5", "value": latest_data.pm25, "unit": "μg/m³", "threshold": env_config.pm25_threshold if env_config else 55.4},
            {"id": "pm10", "label": "PM10", "value": latest_data.pm10, "unit": "μg/m³", "threshold": env_config.pm10_threshold if env_config else 150},
            {"id": "co", "label": "CO", "value": latest_data.co, "unit": "μg/m³", "threshold": env_config.co_threshold if env_config else 8000},
            {"id": "no2", "label": "NO₂", "value": latest_data.no2, "unit": "μg/m³", "threshold": env_config.no2_threshold if env_config else 200},
            {"id": "so2", "label": "SO₂", "value": latest_data.so2, "unit": "μg/m³", "threshold": env_config.so2_threshold if env_config else 180},
            {"id": "o3", "label": "O₃", "value": latest_data.o3, "unit": "μg/m³", "threshold": env_config.o3_threshold if env_config else 235},
        ]

    if hourly_data:
        for h in hourly_data:
            hourly_trend.append({
                "time": h.timestamp.isoformat(),
                "temperature": h.temperature,
                "humidity": h.humidity,
                "pm25": h.pm25,
                "ispu": h.ispu,
            })
        hourly_trend.reverse()

    return {
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "zone": node.zone,
        "online": node.online,
        "lastUpdate": node.last_update.isoformat() if node.last_update else "",
        "sensors": sensors,
        "ispu": ispu_info,
        "hourlyTrend": hourly_trend,
        "envConfig": {
            "tempThreshold": env_config.temp_threshold if env_config else 35.0,
            "humThreshold": env_config.hum_threshold if env_config else 80.0,
            "pm25Threshold": env_config.pm25_threshold if env_config else 55.4,
            "pm10Threshold": env_config.pm10_threshold if env_config else 150.0,
            "coThreshold": env_config.co_threshold if env_config else 8000.0,
            "no2Threshold": env_config.no2_threshold if env_config else 200.0,
            "so2Threshold": env_config.so2_threshold if env_config else 180.0,
            "o3Threshold": env_config.o3_threshold if env_config else 235.0,
        } if env_config else None,
    }


def format_vision_node(node, config, latest_snapshot):
    """Format an AI Vision node with its config and latest detection."""
    vision_config = None
    last_detection = None

    if config:
        vision_config = {
            "streamUrl": config.stream_url or "",
            "roomArea": config.room_area,
            "confidenceThreshold": config.confidence_threshold,
            "densityWarning": config.density_warning,
            "densityAlert": config.density_alert,
        }

    if latest_snapshot:
        last_detection = {
            "personCount": latest_snapshot.person_count,
            "density": latest_snapshot.density,
            "densityLevel": latest_snapshot.density_level,
            "timestamp": latest_snapshot.timestamp.isoformat(),
        }

    return {
        "id": node.id,
        "name": node.name,
        "type": node.type,
        "zone": node.zone,
        "online": node.online,
        "lastUpdate": node.last_update.isoformat() if node.last_update else "",
        "visionConfig": vision_config,
        "lastDetection": last_detection,
    }


def format_gateway_data(db, gateway, accessible_gateways=None):
    """Format a gateway with all its nodes."""
    if accessible_gateways is not None and gateway.id not in accessible_gateways:
        return None

    nodes = crud.get_nodes_by_gateway(db, gateway.id)
    formatted_nodes = []

    for node in nodes:
        if node.type == "environmental":
            env_config = crud.get_env_config(db, node.id)
            hourly_data = crud.get_node_sensor_trend(db, node.id, limit=24)
            latest = hourly_data[0] if hourly_data else None
            formatted_nodes.append(format_env_node(node, env_config, latest, hourly_data))
        elif node.type == "ai_vision":
            config = crud.get_vision_config(db, node.id)
            snapshots = crud.get_vision_snapshots(db, node.id, limit=1)
            latest_snap = snapshots[0] if snapshots else None
            formatted_nodes.append(format_vision_node(node, config, latest_snap))

    return {
        "id": gateway.id,
        "name": gateway.name,
        "location": gateway.location,
        "lat": gateway.lat,
        "lon": gateway.lon,
        "online": gateway.online,
        "lastUpdate": gateway.last_update.isoformat() if gateway.last_update else "",
        "nodes": formatted_nodes,
    }


# ── WebSocket Manager ────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[dict] = []

    async def connect(self, websocket: WebSocket, token: str):
        await websocket.accept()
        try:
            payload = verify_jwt(token)
            if not payload:
                raise Exception("Invalid JWT")
            
            role = payload.get("role")
            company_id = payload.get("company_id")
            accessible_gateways = get_accessible_gateways(company_id, role)

            # Send initial full state
            db = database.SessionLocal()
            try:
                gateways = crud.get_gateways(db)
                db_gw_ids = set([gw.id for gw in gateways])
                results = []
                for gw in gateways:
                    formatted = format_gateway_data(db, gw, accessible_gateways)
                    if formatted:
                        results.append(formatted)

                # Inject claimed but non-existent gateways as offline/empty
                if accessible_gateways is not None:
                    for gw_id in accessible_gateways:
                        if gw_id not in db_gw_ids:
                            results.append({
                                "id": gw_id,
                                "name": f"Gateway {gw_id[-4:]}",
                                "location": "Pending Setup",
                                "lat": -6.200000,
                                "lon": 106.816666,
                                "online": False,
                                "lastUpdate": "",
                                "nodes": []
                            })

                await websocket.send_json({
                    "type": "INITIAL_STATE",
                    "gateways": results,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
            finally:
                db.close()

            self.active_connections.append({
                "ws": websocket,
                "accessible_gateways": accessible_gateways,
            })
            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            await websocket.send_json({"error": f"Unauthorized: {str(e)}"})
            await websocket.close(code=1008)
            return False

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [c for c in self.active_connections if c["ws"] != websocket]

    async def broadcast_gateway_update(self, gateway_id: str):
        """Broadcast updated gateway data to all authorized clients."""
        db = database.SessionLocal()
        try:
            gw = db.query(models.Gateway).filter(models.Gateway.id == gateway_id).first()
            if not gw:
                return

            formatted = format_gateway_data(db, gw)
            if not formatted:
                return

            payload = {
                "type": "GATEWAY_UPDATE",
                "gateway": formatted,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            for conn in self.active_connections:
                acc = conn["accessible_gateways"]
                if acc is None or gateway_id in acc:
                    try:
                        await conn["ws"].send_json(payload)
                    except Exception:
                        pass
        finally:
            db.close()


manager = ConnectionManager()

# Create DB tables
models.Base.metadata.create_all(bind=database.engine)

# Seed warehouse data
db = database.SessionLocal()
try:
    crud.seed_warehouse_data(db)
finally:
    db.close()

app = FastAPI(title="SINERGI Industrial IoT Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start MQTT Client
mqtt_client = None

@app.on_event("startup")
async def startup_event():
    global mqtt_client
    mqtt_client = start_mqtt_client(manager)


# ── WebSocket Endpoint ───────────────────────────────────────────

@app.websocket("/api/v1/ws/stations")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    connected = await manager.connect(websocket, token)
    if not connected:
        return
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── REST Endpoints ───────────────────────────────────────────────

class EnvConfigUpdate(BaseModel):
    temp_threshold: Optional[float] = None
    hum_threshold: Optional[float] = None
    pm25_threshold: Optional[float] = None
    pm10_threshold: Optional[float] = None
    co_threshold: Optional[float] = None
    no2_threshold: Optional[float] = None
    so2_threshold: Optional[float] = None
    o3_threshold: Optional[float] = None

class VisionConfigUpdate(BaseModel):
    stream_url: Optional[str] = None
    room_area: Optional[float] = None
    confidence_threshold: Optional[float] = None
    density_warning: Optional[float] = None
    density_alert: Optional[float] = None


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None


class GatewayUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@app.post("/api/v1/env/config/{node_id}")
def update_env_config(node_id: str, body: EnvConfigUpdate, background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        config = crud.upsert_env_config(db, node_id, body.model_dump(exclude_none=True))
        
        # Find gateway_id to broadcast the update to all connected WebSocket clients
        node = db.query(models.Node).filter(models.Node.id == node_id).first()
        if node and mqtt_client is not None:
            background_tasks.add_task(manager.broadcast_gateway_update, node.gateway_id)

        return {"status": "success", "node_id": config.node_id}
    finally:
        db.close()


@app.put("/api/v1/gateways/{gateway_id}")
def update_gateway_info(gateway_id: str, body: GatewayUpdate, background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        gw = crud.update_gateway_info(db, gateway_id, body.model_dump(exclude_none=True))
        if not gw:
            raise HTTPException(status_code=404, detail="Gateway not found")
        
        # Broadcast gateway update to websocket clients
        if mqtt_client is not None:
            background_tasks.add_task(manager.broadcast_gateway_update, gw.id)
            
        return {"status": "success", "gateway_id": gw.id, "name": gw.name, "lat": gw.lat, "lon": gw.lon}
    finally:
        db.close()


@app.post("/api/v1/nodes/{node_id}")
def update_node_info(node_id: str, body: NodeUpdate, background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        node = crud.update_node_info(db, node_id, body.model_dump(exclude_none=True))
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        
        # Broadcast gateway update
        if mqtt_client is not None:
            background_tasks.add_task(manager.broadcast_gateway_update, node.gateway_id)
            
        return {"status": "success", "node_id": node.id, "name": node.name, "zone": node.zone}
    finally:
        db.close()


@app.get("/")
def read_root():
    return {"status": "ok", "message": "SINERGI Industrial IoT Backend is running"}


@app.get("/api/v1/vision/config/{node_id}")
def get_vision_config(node_id: str):
    db = database.SessionLocal()
    try:
        config = crud.get_vision_config(db, node_id)
        if not config:
            raise HTTPException(status_code=404, detail="Vision config not found")
        return {
            "node_id": config.node_id,
            "stream_url": config.stream_url,
            "room_area": config.room_area,
            "confidence_threshold": config.confidence_threshold,
            "density_warning": config.density_warning,
            "density_alert": config.density_alert,
        }
    finally:
        db.close()


@app.post("/api/v1/vision/config/{node_id}")
def update_vision_config(node_id: str, body: VisionConfigUpdate, background_tasks: BackgroundTasks):
    db = database.SessionLocal()
    try:
        config = crud.upsert_vision_config(db, node_id, body.model_dump(exclude_none=True))
        
        # Find gateway_id to broadcast the update to all connected WebSocket clients
        node = db.query(models.Node).filter(models.Node.id == node_id).first()
        if node and mqtt_client is not None:
            background_tasks.add_task(manager.broadcast_gateway_update, node.gateway_id)

        return {
            "node_id": config.node_id,
            "stream_url": config.stream_url,
            "room_area": config.room_area,
            "confidence_threshold": config.confidence_threshold,
            "density_warning": config.density_warning,
            "density_alert": config.density_alert,
        }
    finally:
        db.close()
