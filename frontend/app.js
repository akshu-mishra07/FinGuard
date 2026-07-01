// FinGuard compliance UI Engine
document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Icons
    lucide.createIcons();

    // 2. DOM Elements
    const canvas = document.getElementById('graph-canvas');
    const ctx = canvas.getContext('2d');
    const graphContainer = document.getElementById('graph-container');
    const graphLoader = document.getElementById('graph-loader');
    
    // Status elements
    const connectionDot = document.getElementById('connection-dot');
    const connectionText = document.getElementById('connection-text');
    
    // Stats elements
    const statNodes = document.getElementById('stat-nodes');
    const statAlerts = document.getElementById('stat-alerts');
    const statLoops = document.getElementById('stat-loops');
    const statRisk = document.getElementById('stat-risk');

    // Controls
    const btnToggleFeed = document.getElementById('btn-toggle-feed');
    const btnReset = document.getElementById('btn-reset');
    const btnInjectLayering = document.getElementById('btn-inject-layering');
    const btnInjectStructuring = document.getElementById('btn-inject-structuring');
    const btnResetLayout = document.getElementById('btn-reset-layout');

    // Lists
    const alertsFeed = document.getElementById('alerts-feed');
    const ledgerFeed = document.getElementById('ledger-feed');

    // Inspectors
    const inspectorPlaceholder = document.getElementById('inspector-placeholder');
    const inspectorContent = document.getElementById('inspector-content');

    // 3. Local State
    let state = {
        nodes: [],
        edges: [],
        transactions: [],
        alerts: [],
        selectedNodeId: null,
        selectedEdgeId: null,
        hoveredNodeId: null,
        draggedNodeId: null,
        simulatorActive: false,
        wsConnected: false
    };

    // Viewport Transformation (Pan / Zoom)
    let transform = { x: 0, y: 0, scale: 1 };
    let isPanning = false;
    let startPan = { x: 0, y: 0 };
    let particles = [];

    const BASE_URL = `http://${window.location.hostname}:8000/api`;
    const WS_URL = `ws://${window.location.hostname}:8000/ws/telemetry`;

    // 4. WebSocket Connectivity
    let ws = null;
    function connectWebSocket() {
        console.log("Connecting to WebSocket:", WS_URL);
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log("WebSocket connection established.");
            state.wsConnected = true;
            connectionDot.className = "dot connected";
            connectionText.innerText = "SOCKET_ESTABLISHED";
            connectionText.className = "status-text connected-text";
            
            // Enable injection buttons
            btnInjectLayering.removeAttribute('disabled');
            btnInjectStructuring.removeAttribute('disabled');
            
            // Fetch initial historical alerts
            fetchHistoricalAlerts();
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'initial_state') {
                    updateGraphData(data.graph_update);
                    hideLoaderIfNodesPresent();
                } else if (data.type === 'new_transaction') {
                    const newTx = data.transaction;
                    
                    // Add to ledger lists
                    state.transactions = [newTx, ...state.transactions].slice(0, 50);
                    if (newTx.is_anomaly) {
                        state.alerts = [newTx, ...state.alerts];
                    }
                    
                    updateGraphData(data.graph_update);
                    renderLedgers();
                    updateGauges();
                    hideLoaderIfNodesPresent();
                } else if (data.type === 'system_reset') {
                    resetLocalState();
                }
            } catch (err) {
                console.error("Error parsing websocket message:", err);
            }
        };

        ws.onclose = () => {
            console.log("WebSocket disconnected. Reconnecting in 4s...");
            state.wsConnected = false;
            connectionDot.className = "dot disconnected";
            connectionText.innerText = "SOCKET_DISCONNECTED";
            connectionText.className = "status-text disconnected-text";
            btnInjectLayering.setAttribute('disabled', 'true');
            btnInjectStructuring.setAttribute('disabled', 'true');
            setTimeout(connectWebSocket, 4000);
        };
    }

    // 5. HTTP Fetch Alerts
    async function fetchHistoricalAlerts() {
        try {
            const res = await fetch(`${BASE_URL}/alerts`);
            if (res.ok) {
                const data = await res.json();
                state.alerts = data;
                renderLedgers();
                updateGauges();
            }
        } catch (err) {
            console.error("Error fetching alerts:", err);
        }
    }

    // 6. API Triggers
    async function toggleSimulator() {
        const action = state.simulatorActive ? 'stop' : 'start';
        try {
            const res = await fetch(`${BASE_URL}/simulator/${action}`, { method: 'POST' });
            if (res.ok) {
                state.simulatorActive = !state.simulatorActive;
                if (state.simulatorActive) {
                    btnToggleFeed.innerHTML = '<i data-lucide="square"></i> Stop Feed';
                    btnToggleFeed.className = "btn btn-rose-outline flex-1";
                } else {
                    btnToggleFeed.innerHTML = '<i data-lucide="play"></i> Run Feed';
                    btnToggleFeed.className = "btn btn-emerald flex-1";
                }
                lucide.createIcons();
            }
        } catch (err) {
            console.error("Error toggling simulator:", err);
        }
    }

    async function injectAttack(type) {
        try {
            await fetch(`${BASE_URL}/simulator/inject/${type}`, { method: 'POST' });
            console.log(`Attack injected: ${type}`);
        } catch (err) {
            console.error("Error injecting attack:", err);
        }
    }

    async function resetEngine() {
        const icon = btnReset.querySelector('i');
        icon.classList.add('animate-spin');
        try {
            const res = await fetch(`${BASE_URL}/reset`, { method: 'POST' });
            if (res.ok) {
                state.simulatorActive = false;
                btnToggleFeed.innerHTML = '<i data-lucide="play"></i> Run Feed';
                btnToggleFeed.className = "btn btn-emerald flex-1";
                lucide.createIcons();
                resetLocalState();
            }
        } catch (err) {
            console.error("Error resetting engine:", err);
        } finally {
            icon.classList.remove('animate-spin');
        }
    }

    function resetLocalState() {
        state.nodes = [];
        state.edges = [];
        state.transactions = [];
        state.alerts = [];
        state.selectedNodeId = null;
        state.selectedEdgeId = null;
        particles = [];
        
        renderLedgers();
        updateGauges();
        closeInspector();
        showLoader();
    }

    // Loader visibility utilities
    function hideLoaderIfNodesPresent() {
        if (state.nodes.length > 0) {
            graphLoader.style.display = 'none';
        } else {
            graphLoader.style.display = 'flex';
        }
    }
    
    function showLoader() {
        graphLoader.style.display = 'flex';
    }

    // 7. Graph Data Synchronization
    function updateGraphData(graphUpdate) {
        const prevNodesMap = new Map(state.nodes.map(n => [n.id, n]));
        const width = canvas.width || 800;
        const height = canvas.height || 500;

        // Merge coordinates
        state.nodes = graphUpdate.nodes.map(node => {
            const prev = prevNodesMap.get(node.id);
            return {
                ...node,
                x: prev?.x ?? (width / 2 + (Math.random() - 0.5) * 150),
                y: prev?.y ?? (height / 2 + (Math.random() - 0.5) * 150),
                vx: prev?.vx ?? 0,
                vy: prev?.vy ?? 0,
                fx: prev?.fx,
                fy: prev?.fy
            };
        });

        state.edges = graphUpdate.edges;

        // Synch cashflow indicator particles
        const newParticles = [];
        state.edges.forEach(edge => {
            const count = edge.is_anomaly ? 3 : 1;
            for (let i = 0; i < count; i++) {
                const matching = particles.find(p => p.edgeId === edge.id);
                newParticles.push({
                    edgeId: edge.id,
                    progress: matching ? (matching.progress + i * 0.3) % 1.0 : Math.random(),
                    speed: edge.is_anomaly ? 0.015 : 0.006
                });
            }
        });
        particles = newParticles;
    }

    // 8. Dynamic Gauges
    function updateGauges() {
        statNodes.innerHTML = `<i data-lucide="network" class="icon-cyan"></i> ${state.nodes.length}`;
        
        // Active alerts count within last 10 minutes
        const activeAlerts = state.alerts.filter(a => {
            const time = new Date(a.timestamp).getTime();
            const limit = Date.now() - 10 * 60 * 1000;
            return time > limit;
        }).length;
        statAlerts.innerHTML = `<i data-lucide="alert-triangle"></i> ${activeAlerts}`;
        
        // Loop count
        const loopCount = state.alerts.filter(a => a.loop_involvement > 0.0).length;
        statLoops.innerHTML = `<i data-lucide="layers"></i> ${loopCount}`;
        
        // Mean risk index
        const avgRisk = state.nodes.length > 0
            ? state.nodes.reduce((acc, curr) => acc + curr.risk_score, 0) / state.nodes.length
            : 0;
        statRisk.innerHTML = `<i data-lucide="trending-up"></i> ${(avgRisk * 100).toFixed(0)}%`;
        
        lucide.createIcons();
    }

    // 9. Render ledgers lists
    function renderLedgers() {
        // High Risk Alerts Feed
        if (state.alerts.length === 0) {
            alertsFeed.innerHTML = '<div class="empty-state">No Anomalies Flagged</div>';
        } else {
            alertsFeed.innerHTML = state.alerts.map(alert => {
                const isSelected = state.selectedEdgeId === (alert._id || alert.id);
                const title = alert.loop_involvement > 0.0 
                    ? 'CIRCULAR_LOOP_DETECTED' 
                    : alert.is_smurfing ? 'SMURFING_ATTACK' : 'VECTOR_SHIFT_ANOMALY';
                
                return `
                    <div class="alert-item ${isSelected ? 'selected' : ''}" data-id="${alert._id || alert.id}">
                        <div class="alert-header">
                            <span>${title}</span>
                            <span>${(alert.risk_score * 100).toFixed(0)}% RISK</span>
                        </div>
                        <div class="alert-link">
                            <span class="truncate">${alert.sender}</span>
                            <i data-lucide="arrow-right"></i>
                            <span class="truncate">${alert.receiver}</span>
                        </div>
                        <div class="alert-footer">
                            <span>$${alert.amount.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                            <span>${new Date(alert.timestamp).toLocaleTimeString()}</span>
                        </div>
                    </div>
                `;
            }).join('');
            
            // Add click listeners to items
            alertsFeed.querySelectorAll('.alert-item').forEach(el => {
                el.addEventListener('click', () => {
                    selectEdge(el.getAttribute('data-id'));
                });
            });
        }

        // Screening Ledger Feed
        if (state.transactions.length === 0) {
            ledgerFeed.innerHTML = '<div class="empty-state font-sans">Ledger Empty</div>';
        } else {
            ledgerFeed.innerHTML = state.transactions.map(tx => {
                const isSelected = state.selectedEdgeId === (tx._id || tx.id);
                return `
                    <div class="ledger-item ${tx.is_anomaly ? 'anomaly' : ''} ${isSelected ? 'selected' : ''}" data-id="${tx._id || tx.id}">
                        <div class="ledger-left">
                            <div class="ledger-link">
                                <span>${tx.sender}</span>
                                <i data-lucide="arrow-right"></i>
                                <span>${tx.receiver}</span>
                            </div>
                            <span class="ledger-time">${new Date(tx.timestamp).toLocaleTimeString()}</span>
                        </div>
                        <div class="ledger-right">
                            <span class="ledger-amount">$${tx.amount.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                            <span class="ledger-badge ${tx.is_anomaly ? 'alert' : 'pass'}">${tx.is_anomaly ? 'ALERT' : 'PASS'}</span>
                        </div>
                    </div>
                `;
            }).join('');

            // Add click listeners to ledger items
            ledgerFeed.querySelectorAll('.ledger-item').forEach(el => {
                el.addEventListener('click', () => {
                    selectEdge(el.getAttribute('data-id'));
                });
            });
        }
        
        lucide.createIcons();
    }

    // 10. Selection & Inspector Handlers
    function selectNode(nodeId) {
        state.selectedNodeId = nodeId;
        state.selectedEdgeId = null;
        renderLedgers();
        
        if (!nodeId) {
            closeInspector();
            return;
        }

        const node = state.nodes.find(n => n.id === nodeId);
        if (!node) return;

        inspectorPlaceholder.classList.add('hidden');
        inspectorContent.classList.remove('hidden');

        inspectorContent.innerHTML = `
            <div class="inspector-detail-card">
                <div>
                    <span class="inspector-field-label">Transacting Identity</span>
                    <span class="inspector-field-val inspector-val-cyan truncate">${node.id}</span>
                </div>

                <div class="inspector-grid-2">
                    <div class="inspector-sub-card">
                        <span class="inspector-sub-card-label">Risk Probability</span>
                        <span class="inspector-sub-card-val ${node.is_flagged ? 'inspector-val-rose' : 'inspector-val-emerald'}">
                            ${(node.risk_score * 100).toFixed(1)}%
                        </span>
                    </div>
                    <div class="inspector-sub-card">
                        <span class="inspector-sub-card-label">Risk Status</span>
                        <span class="inspector-sub-card-val ${node.is_flagged ? 'inspector-val-rose' : 'text-slate-500'}" style="font-size:9px; text-transform: uppercase;">
                            ${node.is_flagged ? 'ISOLATE_ACCOUNT' : 'SCREENED_PASS'}
                        </span>
                    </div>
                </div>

                <div class="inspector-list">
                    <span class="inspector-list-title">Dynamic Risk Cache Matrices</span>
                    <div class="inspector-row-item">
                        <span class="inspector-row-item-label">10m Cash Outflow:</span>
                        <span class="inspector-row-item-val">$${node.velocity_10m.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                    </div>
                    <div class="inspector-row-item">
                        <span class="inspector-row-item-label">10m Transfer Count:</span>
                        <span class="inspector-row-item-val">${node.freq_10m}</span>
                    </div>
                </div>
            </div>
        `;
    }

    function selectEdge(edgeId) {
        state.selectedEdgeId = edgeId;
        state.selectedNodeId = null;
        renderLedgers();

        if (!edgeId) {
            closeInspector();
            return;
        }

        const tx = state.transactions.find(t => t._id === edgeId || t.id === edgeId) ||
                   state.alerts.find(t => t._id === edgeId || t.id === edgeId);
                   
        if (!tx) return;

        inspectorPlaceholder.classList.add('hidden');
        inspectorContent.classList.remove('hidden');

        let extraAnalysisHTML = '';
        if (tx.loop_path) {
            extraAnalysisHTML = `
                <div class="inspector-path-panel mt-3">
                    <div class="inspector-path-label">Isolated Circular Loop Path</div>
                    <div class="inspector-path-row">
                        ${tx.loop_path.map((node, i) => `
                            ${i > 0 ? '<i data-lucide="arrow-right" class="inspector-path-arrow"></i>' : ''}
                            <span class="inspector-path-node" title="${node}">${node}</span>
                        `).join('')}
                    </div>
                </div>
            `;
        } else if (tx.is_smurfing) {
            extraAnalysisHTML = `
                <div class="inspector-smurf-panel mt-3">
                    <div class="inspector-smurf-label">Structuring (Smurfing) Target</div>
                    <span style="font-size: 8px; color: var(--text-slate-500); display: block; margin-bottom: 4px;">Received deposits from:</span>
                    <div class="inspector-smurf-row">
                        ${tx.smurf_accounts.map(node => `
                            <span class="inspector-smurf-node" title="${node}">${node}</span>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        inspectorContent.innerHTML = `
            <div class="inspector-detail-card">
                <div>
                    <span class="inspector-field-label">Transaction Link</span>
                    <div class="alert-link font-bold text-xs" style="margin-top:4px;">
                        <span class="inspector-val-cyan truncate">${tx.sender}</span>
                        <i data-lucide="arrow-right"></i>
                        <span class="inspector-val-cyan truncate">${tx.receiver}</span>
                    </div>
                </div>

                <div class="inspector-grid-2">
                    <div class="inspector-sub-card">
                        <span class="inspector-sub-card-label">Transfer Amount</span>
                        <span class="inspector-sub-card-val text-slate-200" style="display:flex; align-items:center; gap:2px;">
                            $${tx.amount.toLocaleString(undefined, {minimumFractionDigits: 2})}
                        </span>
                    </div>
                    <div class="inspector-sub-card">
                        <span class="inspector-sub-card-label">Ensemble Risk</span>
                        <span class="inspector-sub-card-val ${tx.is_anomaly ? 'inspector-val-rose' : 'inspector-val-emerald'}">
                            ${(tx.risk_score * 100).toFixed(1)}%
                        </span>
                    </div>
                </div>

                <div class="inspector-list">
                    <span class="inspector-list-title">AI Layer Stat Scores</span>
                    <div class="inspector-row-item" title="Mean Squared Error of PyTorch Autoencoder">
                        <span class="inspector-row-item-label">Autoencoder MSE:</span>
                        <span class="inspector-row-item-val">${tx.ae_mse.toFixed(6)}</span>
                    </div>
                    <div class="inspector-row-item" title="Isolation Forest outlier score">
                        <span class="inspector-row-item-label">Isolation Forest Score:</span>
                        <span class="inspector-row-item-val">${tx.if_score.toFixed(6)}</span>
                    </div>
                </div>

                ${extraAnalysisHTML}
            </div>
        `;
        
        lucide.createIcons();
    }

    function closeInspector() {
        inspectorPlaceholder.classList.remove('hidden');
        inspectorContent.classList.add('hidden');
        inspectorContent.innerHTML = '';
    }

    // 11. Canvas Force-Directed Layout Simulation Loop
    function handleResize() {
        canvas.width = graphContainer.clientWidth;
        canvas.height = graphContainer.clientHeight;
    }
    
    window.addEventListener('resize', handleResize);
    handleResize();

    function runSimulation() {
        const width = canvas.width;
        const height = canvas.height;

        // 1. Force physics parameters
        const kAttract = 0.04;
        const kRepel = 400.0;
        const gravity = 0.02;
        const damping = 0.85;
        const restLength = 120;

        // Apply node-to-node repulsion
        for (let i = 0; i < state.nodes.length; i++) {
            const u = state.nodes[i];
            if (u.fx !== undefined) continue;

            for (let j = 0; j < state.nodes.length; j++) {
                if (i === j) continue;
                const v = state.nodes[j];

                const dx = u.x - v.x;
                const dy = u.y - v.y;
                let dist = Math.sqrt(dx * dx + dy * dy);
                if (dist === 0) dist = 0.1;

                const f = kRepel / (dist * dist);
                u.vx += (dx / dist) * f;
                u.vy += (dy / dist) * f;
            }

            // Central gravity
            const cx = width / 2;
            const cy = height / 2;
            u.vx -= (u.x - cx) * gravity;
            u.vy -= (u.y - cy) * gravity;
        }

        // Apply edge attractions
        const nodeMap = new Map(state.nodes.map(n => [n.id, n]));
        state.edges.forEach(edge => {
            const u = nodeMap.get(edge.source);
            const v = nodeMap.get(edge.target);
            if (!u || !v) return;

            const dx = v.x - u.x;
            const dy = v.y - u.y;
            let dist = Math.sqrt(dx * dx + dy * dy);
            if (dist === 0) dist = 0.1;

            const force = kAttract * (dist - restLength);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;

            if (u.fx === undefined) {
                u.vx += fx;
                u.vy += fy;
            }
            if (v.fx === undefined) {
                v.vx -= fx;
                v.vy -= fy;
            }
        });

        // Update positions
        state.nodes.forEach(node => {
            if (node.fx !== undefined) {
                node.x = node.fx;
                node.y = node.fy;
                node.vx = 0;
                node.vy = 0;
            } else {
                node.x += node.vx;
                node.y += node.vy;
                node.vx *= damping;
                node.vy *= damping;

                // boundaries constraint
                const margin = 40;
                node.x = Math.max(margin, Math.min(width - margin, node.x));
                node.y = Math.max(margin, Math.min(height - margin, node.y));
            }
        });

        // 2. Render Scene
        ctx.clearRect(0, 0, width, height);
        ctx.save();
        
        // Panning/Zooming
        ctx.translate(transform.x, transform.y);
        ctx.scale(transform.scale, transform.scale);

        const activeId = state.selectedNodeId || state.hoveredNodeId;
        const isNodeDimmed = (nodeId) => {
            if (!activeId) return false;
            if (nodeId === activeId) return false;
            return !state.edges.some(
                edge => (edge.source === activeId && edge.target === nodeId) ||
                        (edge.target === activeId && edge.source === nodeId)
            );
        };

        const isEdgeDimmed = (edge) => {
            if (state.selectedEdgeId === edge.id) return false;
            if (!activeId) return false;
            return edge.source !== activeId && edge.target !== activeId;
        };

        // Draw connection lines (edges)
        state.edges.forEach(edge => {
            const u = nodeMap.get(edge.source);
            const v = nodeMap.get(edge.target);
            if (!u || !v) return;

            const dimmed = isEdgeDimmed(edge);
            ctx.beginPath();
            ctx.moveTo(u.x, u.y);
            ctx.lineTo(v.x, v.y);

            if (edge.is_anomaly || edge.loop_involvement > 0) {
                ctx.strokeStyle = dimmed ? 'rgba(239, 68, 68, 0.15)' : (state.selectedEdgeId === edge.id ? '#ff2a5f' : '#ef4444');
                ctx.lineWidth = state.selectedEdgeId === edge.id ? 4.5 : 2.5;
                ctx.shadowColor = '#ef4444';
                ctx.shadowBlur = dimmed ? 0 : 12;
            } else {
                ctx.strokeStyle = dimmed ? 'rgba(71, 85, 105, 0.15)' : 'rgba(71, 85, 105, 0.6)';
                ctx.lineWidth = state.selectedEdgeId === edge.id ? 3.0 : 1.2;
                ctx.shadowBlur = 0;
            }

            ctx.stroke();
            ctx.shadowBlur = 0; // reset
        });

        // Draw flowing cash particles
        particles.forEach(p => {
            const edge = state.edges.find(e => e.id === p.edgeId);
            if (!edge) return;

            const u = nodeMap.get(edge.source);
            const v = nodeMap.get(edge.target);
            if (!u || !v) return;

            p.progress = (p.progress + p.speed) % 1.0;
            if (isEdgeDimmed(edge)) return;

            const px = u.x + (v.x - u.x) * p.progress;
            const py = u.y + (v.y - u.y) * p.progress;

            ctx.beginPath();
            ctx.arc(px, py, edge.is_anomaly ? 4.0 : 2.5, 0, Math.PI * 2);
            ctx.fillStyle = edge.is_anomaly ? '#ff003c' : '#06b6d4';

            if (edge.is_anomaly) {
                ctx.shadowColor = '#ff003c';
                ctx.shadowBlur = 10;
            }
            ctx.fill();
            ctx.shadowBlur = 0;
        });

        // Draw Account circles (nodes)
        state.nodes.forEach(node => {
            const dimmed = isNodeDimmed(node.id);
            const isSelected = state.selectedNodeId === node.id;
            const isHovered = state.hoveredNodeId === node.id;
            const radius = node.is_flagged ? 18 : 12;

            if (node.is_flagged) {
                ctx.beginPath();
                ctx.arc(node.x, node.y, radius + 4 + Math.sin(Date.now() * 0.008) * 2, 0, Math.PI * 2);
                ctx.strokeStyle = dimmed ? 'rgba(239, 68, 68, 0.1)' : 'rgba(239, 68, 68, 0.5)';
                ctx.lineWidth = 1.5;
                ctx.stroke();
            }

            ctx.beginPath();
            ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);

            if (node.is_flagged) {
                ctx.fillStyle = dimmed ? '#4c0519' : '#e11d48';
                ctx.strokeStyle = '#f43f5e';
                ctx.lineWidth = isSelected || isHovered ? 3.0 : 1.5;
                ctx.shadowColor = '#f43f5e';
                ctx.shadowBlur = dimmed ? 0 : 12;
            } else {
                ctx.fillStyle = dimmed ? '#0f172a' : '#1e293b';
                ctx.strokeStyle = dimmed ? 'rgba(6, 182, 212, 0.2)' : (isSelected || isHovered ? '#06b6d4' : '#475569');
                ctx.lineWidth = isSelected || isHovered ? 2.5 : 1.5;
                ctx.shadowBlur = isHovered ? 8 : 0;
                ctx.shadowColor = '#06b6d4';
            }

            ctx.fill();
            ctx.stroke();
            ctx.shadowBlur = 0;

            // Draw text label
            ctx.font = isSelected || isHovered ? 'bold 11px Inter, sans-serif' : '10px Inter, sans-serif';
            ctx.fillStyle = node.is_flagged
                ? (dimmed ? 'rgba(244, 63, 94, 0.4)' : '#f43f5e')
                : (dimmed ? 'rgba(148, 163, 184, 0.3)' : '#cbd5e1');
            ctx.textAlign = 'center';
            ctx.fillText(node.id, node.x, node.y - radius - 6);

            if (isSelected) {
                ctx.font = '9px Inter, sans-serif';
                ctx.fillStyle = '#64748b';
                ctx.fillText(`Risk: ${(node.risk_score * 100).toFixed(0)}%`, node.x, node.y + radius + 12);
            }
        });

        ctx.restore();
        requestAnimationFrame(runSimulation);
    }
    requestAnimationFrame(runSimulation);

    // 12. Mouse Events & Canvas interaction
    function getMouseCoords(e) {
        const rect = canvas.getBoundingClientRect();
        const rawX = e.clientX - rect.left;
        const rawY = e.clientY - rect.top;
        
        const x = (rawX - transform.x) / transform.scale;
        const y = (rawY - transform.y) / transform.scale;
        return { x, y, rawX, rawY };
    }

    canvas.addEventListener('mousedown', (e) => {
        const { x, y, rawX, rawY } = getMouseCoords(e);
        let clickedNodeId = null;

        for (let i = state.nodes.length - 1; i >= 0; i--) {
            const node = state.nodes[i];
            const radius = node.is_flagged ? 18 : 12;
            const dx = node.x - x;
            const dy = node.y - y;
            if (dx * dx + dy * dy <= radius * radius) {
                clickedNodeId = node.id;
                break;
            }
        }

        if (clickedNodeId) {
            state.draggedNodeId = clickedNodeId;
            selectNode(clickedNodeId);
            
            const node = state.nodes.find(n => n.id === clickedNodeId);
            if (node) {
                node.fx = x;
                node.fy = y;
            }
        } else {
            // Check edge clicks
            let clickedEdgeId = null;
            const nodeMap = new Map(state.nodes.map(n => [n.id, n]));

            for (const edge of state.edges) {
                const u = nodeMap.get(edge.source);
                const v = nodeMap.get(edge.target);
                if (!u || !v) continue;

                const l2 = (v.x - u.x) ** 2 + (v.y - u.y) ** 2;
                if (l2 === 0) continue;

                let t = ((x - u.x) * (v.x - u.x) + (y - u.y) * (v.y - u.y)) / l2;
                t = Math.max(0, Math.min(1, t));

                const projX = u.x + t * (v.x - u.x);
                const projY = u.y + t * (v.y - u.y);
                const distSq = (x - projX) ** 2 + (y - projY) ** 2;
                
                if (distSq < 36) { // 6px threshold
                    clickedEdgeId = edge.id;
                    break;
                }
            }

            if (clickedEdgeId) {
                selectEdge(clickedEdgeId);
            } else {
                isPanning = true;
                startPan = { x: rawX - transform.x, y: rawY - transform.y };
                selectNode(null);
            }
        }
    });

    canvas.addEventListener('mousemove', (e) => {
        const { x, y, rawX, rawY } = getMouseCoords(e);

        if (state.draggedNodeId) {
            const node = state.nodes.find(n => n.id === state.draggedNodeId);
            if (node) {
                node.fx = x;
                node.fy = y;
            }
            return;
        }

        if (isPanning) {
            transform.x = rawX - startPan.x;
            transform.y = rawY - startPan.y;
            return;
        }

        // Hover detection
        let hoverId = null;
        for (let i = state.nodes.length - 1; i >= 0; i--) {
            const node = state.nodes[i];
            const radius = node.is_flagged ? 18 : 12;
            const dx = node.x - x;
            const dy = node.y - y;
            if (dx * dx + dy * dy <= radius * radius) {
                hoverId = node.id;
                break;
            }
        }
        state.hoveredNodeId = hoverId;
    });

    canvas.addEventListener('mouseup', () => {
        if (state.draggedNodeId) {
            const node = state.nodes.find(n => n.id === state.draggedNodeId);
            if (node) {
                node.fx = undefined;
                node.fy = undefined;
            }
            state.draggedNodeId = null;
        }
        isPanning = false;
    });

    canvas.addEventListener('mouseleave', () => {
        if (state.draggedNodeId) {
            const node = state.nodes.find(n => n.id === state.draggedNodeId);
            if (node) {
                node.fx = undefined;
                node.fy = undefined;
            }
            state.draggedNodeId = null;
        }
        isPanning = false;
    });

    canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const zoomIntensity = 0.08;
        const { rawX, rawY } = getMouseCoords(e);

        const zoomFactor = e.deltaY < 0 ? (1 + zoomIntensity) : (1 - zoomIntensity);
        const newScale = Math.min(2.5, Math.max(0.4, transform.scale * zoomFactor));

        transform.x = rawX - (rawX - transform.x) * (newScale / transform.scale);
        transform.y = rawY - (rawY - transform.y) * (newScale / transform.scale);
        transform.scale = newScale;
    }, { passive: false });

    btnResetLayout.addEventListener('click', () => {
        transform = { x: 0, y: 0, scale: 1 };
        const width = canvas.width;
        const height = canvas.height;
        state.nodes.forEach(node => {
            node.x = width / 2 + (Math.random() - 0.5) * 200;
            node.y = height / 2 + (Math.random() - 0.5) * 200;
            node.vx = 0;
            node.vy = 0;
        });
    });

    // 13. Event Dispatch Hookups
    btnToggleFeed.addEventListener('click', toggleSimulator);
    btnReset.addEventListener('click', resetEngine);
    btnInjectLayering.addEventListener('click', () => injectAttack('layering'));
    btnInjectStructuring.addEventListener('click', () => injectAttack('structuring'));

    // Start WebSocket
    connectWebSocket();
});
