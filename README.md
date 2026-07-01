# FinGuard: Real-Time Anti-Money Laundering (AML) & Transaction Fraud Graph Analyzer

FinGuard is a high-throughput streaming ledger system that screens active transfers, builds transaction link graphs, and automatically isolates high-risk structural fraud paths.

---

## 🛠️ System Architecture
1. **The AI Layer (`backend/ai_model.py`)**: Implement an Isolation Forest combined with an Autoencoder Neural Network trained using PyTorch to calculate real-time spatial statistical vector shifts across user transaction behavior.
2. **The Backend & DB (`backend/`)**: FastAPI uses Python’s asyncio to read high-velocity transfer request queues concurrently. MongoDB stores the polymorphic transacting identity parameters, caching computed user risk velocity matrices dynamically.
3. **The UI (`frontend/`)**: A full-featured dark-mode financial compliance dashboard using a canvas to draw account linkages, highlighting suspicious transfer chains in glowing red vectors.

---

## 🚀 Quick Start Instructions

### 1. Prerequisite Installations
- **Python 3.9+**
- **MongoDB** running locally on port `27017`

### 2. Setup the Backend
Navigate to the `backend/` directory, create a virtual environment, and install dependencies:
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# If you get a motor/pymongo compatibility import error, run:
pip install pymongo==4.6.3
```

### 3. Run the Backend Server
Start the FastAPI server:
```bash
uvicorn main:app --reload --port 8000
```
Upon startup, the server connects to MongoDB, auto-calibrates the PyTorch Autoencoder and Isolation Forest models on baseline datasets, and opens a WebSocket stream on port `8000`.

### 4. Open the Compliance UI Dashboard
No compilation or server hosting is required for the UI. Simply open the file:
```text
frontend/index.html
```
in any modern web browser (e.g. Double-click the file or open it in Chrome/Safari).

---

## 🔬 Interactive Simulation
On the dashboard:
1. Click **Run Feed** to stream background retail transactions.
2. Click **Inject Circular Loop** to inject a multi-hop circular money routing attack. Watch the graph engine isolate the cycle path and illuminate the link connections in glowing neon red vectors.
3. Click **Inject Structuring (Smurf)** to simulate multiple small accounts funneling cash to a single merchant node.
4. Click on any account circle or transaction line to display detailed PyTorch Autoencoder MSE losses, Isolation Forest outlier scores, and isolated path configurations in the **AML Diagnostic Inspector** sidebar.
