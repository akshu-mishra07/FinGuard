# FinGuard: Real-Time Anti-Money Laundering (AML) & Transaction Fraud Graph Analyzer

**FinGuard** is a high-throughput transaction screening and structural fraud path isolation platform. It detects complex money laundering patterns (e.g., circular layering, structuring, and smurfing) using a hybrid ensemble of PyTorch-based Autoencoders, scikit-learn Isolation Forests, and graphcycle-detection pathfinding.

---

## 📋 Executive Summary
Modern financial cybercriminals bypass traditional single-card rule triggers by routing funds through multi-account structural networks (mule chains) and breaking down large sums into minor transfers (structuring). 

FinGuard resolves this by:
1. **Streaming Ledger Screening**: Ingesting high-velocity transactions concurrently via FastAPI and asyncio queues.
2. **Hybrid ML Vector Shifts**: Analyzing statistical anomalies using a PyTorch Autoencoder to measure spatial vector shifts (reconstruction loss) alongside an Isolation Forest.
3. **Graph Topology Analysis**: Detecting directed loops (circular layering) and high-inflow consolidations (smurfing) in real-time.
4. **Interactive Forensics UI**: Animating real-time money transfers on an HTML5 physics Canvas, displaying isolated fraud paths as glowing neon red vectors.

---

## 🛠️ System Architecture

```
                                  +---------------------------------------+
                                  |      Next.js Compliance Client        |
                                  |    (Canvas Graph & Telemetry UI)      |
                                  +---------------------------------------+
                                        ^                          |
                             WebSockets | (Real-Time Streams)      | HTTP REST (Trigger SIM)
                                        |                          v
                                  +---------------------------------------+
                                  |         FastAPI Ingestion             |
                                  +---------------------------------------+
                                        |
                                  +-----v-----+
                                  |  asyncio  | (Concurrently buffers active
                                  |   Queue   |  transaction streams)
                                  +-----+-----+
                                        |
                                  +-----v-----+
                                  | Ingestion |
                                  |  Worker   |
                                  +-----+-----+
                                        |
                 +----------------------+----------------------+
                 |                                             |
      +----------v----------+                       +----------v----------+
      |  Graph Cycle DFS    |                       |      AI Ensemble    |
      |   Path Analyzer     |                       |  PyTorch AE + Sk IF |
      +----------+----------+                       +----------+----------+
                 |                                             |
                 +----------------------+----------------------+
                                        | (Dynamic Cache matrices)
                                  +-----v-----+
                                  |  MongoDB  | (Collections: transactions,
                                  |  Database |  identities)
                                  +-----------+
```

---

## 🤖 The AI Layer

### 1. PyTorch Autoencoder
The Autoencoder neural network acts as a **spatial vector shift detector**. It compresses 8 transaction features into a 4-dimensional latent bottleneck and attempts to reconstruct them. When a user behaves anomalously (e.g., a massive spike in velocity or out-degree), the network struggles to reconstruct the features, resulting in a high Mean Squared Error (MSE).

- **Input Dimension**: 8 (Amount, Velocity 1m, Velocity 10m, Frequency 1m, Frequency 10m, Out-degree, In-degree, Loop involvement)
- **Latent Bottleneck Dimension**: 4
- **Loss Function**: Mean Squared Error (MSE)
- **Optimizer**: Adam (lr=0.01)

### 2. Isolation Forest
Fits an ensemble of isolation trees to segment anomalous points. It works recursively: normal points require many partitions to isolate, whereas outliers isolate very quickly (closer to the root of the tree).

- **Combined Ensemble Risk Score**: The system scales the outputs of both the Autoencoder reconstruction loss and the Isolation Forest decision boundary to a `[0.0, 1.0]` probability index. The final risk index is:
  $$\text{Risk Score} = \max(\text{Autoencoder Risk}, \text{Isolation Forest Risk})$$
  If a structural loop is detected by the Graph Engine, the risk score is automatically escalated to a critical **98% (0.98)**.

---

## 🕸️ Graph Cycle & Loop Analyzer
Standard transaction processing engines fail to catch circular loop transfers. FinGuard constructs an in-memory directed graph of transactions occurring within a rolling 10-minute window.

1. **Cycle Detection**: For every transaction from sender $S$ to receiver $R$, the engine performs a Depth-First Search (DFS) from $R$ back to $S$.
2. **Reconstitution**: If a path is found (e.g., $R \rightarrow X \rightarrow Y \rightarrow S$), adding the link $S \rightarrow R$ creates a directed loop.
3. **Loop Isolation**: The path `[S, R, X, Y, S]` is flagged, and the connections are drawn as glowing red vectors on the canvas.

---

## 🗄️ Database & Cache Schema

FinGuard connects to MongoDB and operates two primary collections under the `finguard` database:

### 1. `transactions`
Stores every screened transfer log:
```json
{
  "_id": "ObjectId",
  "timestamp": "ISODate",
  "sender": "string (Account ID)",
  "receiver": "string (Account ID)",
  "amount": "float",
  "risk_score": "float (0.0 to 1.0)",
  "ae_mse": "float",
  "if_score": "float",
  "is_anomaly": "boolean",
  "loop_involvement": "float (0.0 or 1.0)",
  "loop_path": "array of strings or null",
  "is_smurfing": "boolean",
  "smurf_accounts": "array of strings"
}
```

### 2. `identities`
Caches the dynamic user risk matrices to prevent heavy queries during high-velocity streams:
```json
{
  "_id": "ObjectId",
  "account_id": "string (Unique)",
  "risk_score": "float",
  "velocity_10m": "float (aggregated cash flow)",
  "freq_10m": "int (transfer frequency)",
  "is_flagged": "boolean",
  "last_updated": "ISODate"
}
```

---

## 🖥️ Live Compliance Dashboard

The UI is built as an integrated dark-mode dashboard at `/finguard` inside the monorepo Next.js app:
1. **Interactive Physics Graph**: Implemented on an HTML5 2D Canvas with force-directed physics. Drag accounts, pan, and zoom.
2. **Glowing Vectors & Particles**: Normal connections show cyan particles moving from sender to receiver. Anomalous connections glow red, with fast-moving red flow particles.
3. **Forensic Panel**: Select any node or edge to inspect the exact PyTorch loss metrics, Isolation Forest score, and trace cycle routes.
4. **Simulator Controller**: Trigger normal activity streams, or inject circular loops and smurfing attacks.
