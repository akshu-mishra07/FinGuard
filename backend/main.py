import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import FinguardDatabase
from ai_model import FinguardAIEnsemble
from graph_analyzer import FinguardGraphAnalyzer
from simulator import FinancialSimulator

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("finguard.main")

# Global instances
db = FinguardDatabase()
ai_ensemble = FinguardAIEnsemble()
transaction_queue = asyncio.Queue()
active_websockets: Set[WebSocket] = set()

# Callback for simulator
async def queue_transaction(sender: str, receiver: str, amount: float):
    tx_req = TransactionRequest(sender=sender, receiver=receiver, amount=amount)
    await transaction_queue.put(tx_req)

simulator = FinancialSimulator(submit_transaction_cb=queue_transaction)

class TransactionRequest(BaseModel):
    sender: str = Field(..., min_length=3, max_length=50)
    receiver: str = Field(..., min_length=3, max_length=50)
    amount: float = Field(..., gt=0.0)

# Background task to process transaction queue
async def transaction_worker():
    logger.info("Transaction ingestion worker started.")
    try:
        while True:
            tx_req = await transaction_queue.get()
            try:
                await process_transaction(tx_req)
            except Exception as e:
                logger.error(f"Error processing transaction {tx_req}: {str(e)}", exc_info=True)
            finally:
                transaction_queue.task_done()
    except asyncio.CancelledError:
        logger.info("Transaction ingestion worker stopping.")

async def process_transaction(tx: TransactionRequest):
    # 1. Fetch recent transactions (last 10 minutes) for calculations
    recent_txs = await db.get_recent_transactions(window_minutes=10)
    
    # 2. Extract sender-specific transactions for velocity matrices
    sender_recent = [t for t in recent_txs if t.get("sender") == tx.sender]
    now = datetime.utcnow()
    
    # Rolling 1m vs 10m metrics
    s_vol_1m = sum(t["amount"] for t in sender_recent if (now - t["timestamp"]).total_seconds() <= 60)
    s_vol_10m = sum(t["amount"] for t in sender_recent)
    s_freq_1m = sum(1 for t in sender_recent if (now - t["timestamp"]).total_seconds() <= 60)
    s_freq_10m = len(sender_recent)
    
    # Add current transaction values into features
    s_vol_1m += tx.amount
    s_vol_10m += tx.amount
    s_freq_1m += 1
    s_freq_10m += 1
    
    # 3. Graph Degree Analysis
    sender_degrees = FinguardGraphAnalyzer.analyze_node_degrees(recent_txs, tx.sender)
    receiver_degrees = FinguardGraphAnalyzer.analyze_node_degrees(recent_txs, tx.receiver)
    
    # Calculate out-degree of sender (plus the new receiver)
    out_degree = sender_degrees["out_degree"]
    if tx.receiver not in sender_degrees["unique_receivers"]:
        out_degree += 1
        
    # Calculate in-degree of receiver (plus the new sender)
    in_degree = receiver_degrees["in_degree"]
    if tx.sender not in receiver_degrees["unique_senders"]:
        in_degree += 1
        
    # 4. Cycle / Structural Loop Detection
    loop_path = FinguardGraphAnalyzer.detect_cycles(recent_txs, tx.sender, tx.receiver)
    loop_involvement = 1.0 if loop_path else 0.0
    
    # 5. Build AI Feature Vector (8 dimensions)
    # [amount, velocity_1m, velocity_10m, freq_1m, freq_10m, out_degree, in_degree, loop_involvement]
    features = [
        tx.amount,
        s_vol_1m,
        s_vol_10m,
        float(s_freq_1m),
        float(s_freq_10m),
        float(out_degree),
        float(in_degree),
        loop_involvement
    ]
    
    # 6. Execute ML Scorer Inference (PyTorch Autoencoder + Isolation Forest)
    prediction = ai_ensemble.predict(features)
    
    risk_score = prediction["risk_score"]
    ae_mse = prediction["ae_mse"]
    if_score = prediction["if_score"]
    is_anomaly = prediction["is_anomaly"]
    
    # Override/Escalate risk score if structural loop detected
    if loop_involvement == 1.0:
        risk_score = max(risk_score, 0.98)
        is_anomaly = True
        
    # 7. Check Smurfing / Structuring Pattern
    smurfing_analysis = FinguardGraphAnalyzer.check_smurfing_pattern(recent_txs, tx.receiver)
    is_smurfing = smurfing_analysis["is_smurfing"]
    if is_smurfing:
        risk_score = max(risk_score, 0.85)
        is_anomaly = True
        
    # 8. Create Transaction Document
    tx_doc = {
        "timestamp": now,
        "sender": tx.sender,
        "receiver": tx.receiver,
        "amount": tx.amount,
        "risk_score": risk_score,
        "ae_mse": ae_mse,
        "if_score": if_score,
        "is_anomaly": is_anomaly,
        "loop_involvement": loop_involvement,
        "loop_path": loop_path,
        "is_smurfing": is_smurfing,
        "smurf_accounts": smurfing_analysis["smurf_accounts"] if is_smurfing else []
    }
    
    # Insert in DB
    tx_id = await db.insert_transaction(tx_doc)
    
    # Format datetime for JSON representation
    tx_doc_serializable = {
        "id": tx_id,
        "_id": tx_id,
        "timestamp": now.isoformat(),
        "sender": tx.sender,
        "receiver": tx.receiver,
        "amount": tx.amount,
        "risk_score": risk_score,
        "ae_mse": ae_mse,
        "if_score": if_score,
        "is_anomaly": is_anomaly,
        "loop_involvement": loop_involvement,
        "loop_path": loop_path,
        "is_smurfing": is_smurfing,
        "smurf_accounts": smurfing_analysis["smurf_accounts"] if is_smurfing else []
    }
    
    # 9. Update Dynamic Identity Cache
    # We update cached user matrices for transacting parties
    sender_identity_metrics = {
        "risk_score": risk_score if tx_doc["is_anomaly"] else 0.1,
        "velocity_10m": s_vol_10m,
        "freq_10m": s_freq_10m,
        "is_flagged": is_anomaly
    }
    await db.update_identity_cache(tx.sender, sender_identity_metrics)
    
    # Receiver's metrics recalculation
    r_recent = [t for t in recent_txs if t.get("receiver") == tx.receiver] + [tx_doc]
    r_vol_10m = sum(t["amount"] for t in r_recent)
    r_freq_10m = len(r_recent)
    receiver_identity_metrics = {
        "risk_score": risk_score if tx_doc["is_anomaly"] else 0.1,
        "velocity_10m": r_vol_10m,
        "freq_10m": r_freq_10m,
        "is_flagged": is_anomaly or is_smurfing
    }
    await db.update_identity_cache(tx.receiver, receiver_identity_metrics)
    
    # 10. Broadcast Telemetry to Connected WebSockets
    await broadcast_telemetry({
        "type": "new_transaction",
        "transaction": tx_doc_serializable,
        "graph_update": await get_graph_data()
    })

async def get_graph_data():
    """
    Builds nodes and edges representing the active 10-minute transaction graph.
    """
    recent_txs = await db.get_recent_transactions(window_minutes=10)
    identities = await db.get_all_identities()
    
    identity_map = {id_doc["account_id"]: id_doc for id_doc in identities}
    
    nodes = {}
    edges = []
    
    # Track accounts from recent transactions
    for tx in recent_txs:
        sender = tx["sender"]
        receiver = tx["receiver"]
        
        for acc in (sender, receiver):
            if acc not in nodes:
                id_data = identity_map.get(acc, {})
                nodes[acc] = {
                    "id": acc,
                    "risk_score": id_data.get("risk_score", 0.05),
                    "velocity_10m": id_data.get("velocity_10m", 0.0),
                    "freq_10m": id_data.get("freq_10m", 0),
                    "is_flagged": id_data.get("is_flagged", False)
                }
                
        # Create unique link edge representation
        edges.append({
            "id": tx["_id"],
            "source": sender,
            "target": receiver,
            "amount": tx["amount"],
            "risk_score": tx.get("risk_score", 0.0),
            "is_anomaly": tx.get("is_anomaly", False),
            "loop_involvement": tx.get("loop_involvement", 0.0),
            "is_smurfing": tx.get("is_smurfing", False)
        })
        
    return {
        "nodes": list(nodes.values()),
        "edges": edges
    }

async def broadcast_telemetry(message: Dict[str, Any]):
    if not active_websockets:
        return
    
    payload = json.dumps(message)
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(ws)
            
    for ws in disconnected:
        active_websockets.remove(ws)

# Lifespan context manager for FastAPI 0.93+
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    logger.info("Initializing FinGuard backend systems...")
    await db.connect()
    
    # Train the PyTorch & Sklearn models on normal baseline data
    ai_ensemble.fit(epochs=20)
    
    # Start ingestion worker background task
    app.state.worker_task = asyncio.create_task(transaction_worker())
    
    yield
    
    # Shutdown tasks
    logger.info("Shutting down FinGuard backend systems...")
    await simulator.stop()
    app.state.worker_task.cancel()
    try:
        await app.state.worker_task
    except asyncio.CancelledError:
        pass
    await db.close()

app = FastAPI(
    title="FinGuard API",
    description="Real-Time AML & Transaction Fraud Graph Analyzer Backend",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In development, allow NextJS frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/transactions")
async def create_transaction(tx: TransactionRequest):
    """
    Submits a transaction to the screening ledger queue.
    """
    await transaction_queue.put(tx)
    return {"status": "queued", "message": "Transaction entered streaming ingestion pipeline."}


@app.get("/api/graph")
async def get_graph():
    """
    Retrieves the current transaction graph visualization payload.
    """
    return await get_graph_data()


@app.get("/api/alerts")
async def get_alerts():
    """
    Fetches flagged anomalies from the transaction database.
    """
    recent_txs = await db.get_recent_transactions(window_minutes=10)
    alerts = [t for t in recent_txs if t.get("is_anomaly")]
    # Convert datetime objects to ISO strings
    for alert in alerts:
        if isinstance(alert.get("timestamp"), datetime):
            alert["timestamp"] = alert["timestamp"].isoformat()
    # Sort alerts by risk score descending
    alerts.sort(key=lambda x: x.get("risk_score", 0.0), reverse=True)
    return alerts


@app.post("/api/simulator/start")
async def start_simulator():
    await simulator.start()
    return {"status": "active", "message": "Transaction simulator started."}


@app.post("/api/simulator/stop")
async def stop_simulator():
    await simulator.stop()
    return {"status": "inactive", "message": "Transaction simulator stopped."}


@app.post("/api/simulator/inject/layering")
async def inject_layering(background_tasks: BackgroundTasks, amount: float = 12500.0):
    background_tasks.add_task(simulator.inject_circular_layering_attack, amount)
    return {"status": "injecting", "message": "Circular layering loop injection initiated."}


@app.post("/api/simulator/inject/structuring")
async def inject_structuring(background_tasks: BackgroundTasks):
    background_tasks.add_task(simulator.inject_structuring_attack)
    return {"status": "injecting", "message": "Structuring smurf attack injection initiated."}


@app.post("/api/reset")
async def reset_system():
    """
    Resets the database and recalibrates the AI model.
    """
    await simulator.stop()
    # Empty queue
    while not transaction_queue.empty():
        try:
            transaction_queue.get_nowait()
            transaction_queue.task_done()
        except asyncio.QueueEmpty:
            break
            
    await db.clear_database()
    ai_ensemble.fit(epochs=20)
    
    # Broadcast reset event
    await broadcast_telemetry({
        "type": "system_reset",
        "graph_update": {"nodes": [], "edges": []}
    })
    
    return {"status": "reset", "message": "Database cleared and AI models recalibrated."}


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(active_websockets)}")
    
    try:
        # Send initial graph data
        graph_data = await get_graph_data()
        await websocket.send_text(json.dumps({
            "type": "initial_state",
            "graph_update": graph_data
        }))
        
        # Keep connection open and respond to heartbeats
        while True:
            data = await websocket.receive_text()
            # Simple heartbeat ping
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
    finally:
        active_websockets.discard(websocket)
        logger.info(f"WebSocket connection closed. Total clients: {len(active_websockets)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
