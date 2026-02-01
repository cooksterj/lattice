/**
 * Lattice Graph Visualization
 * D3.js force-directed graph with interactive features
 */

// Neon Grid color palette for asset groups
const GROUP_COLORS = {
    default: {start: '#7b2cbf', end: '#3c096c', stroke: '#9d4edd'},    // Purple
    analytics: {start: '#05d9e8', end: '#01949a', stroke: '#05d9e8'},  // Cyan
    data: {start: '#ff2a6d', end: '#b5179e', stroke: '#ff2a6d'},       // Pink
    ml: {start: '#f6ff00', end: '#d4af00', stroke: '#f6ff00'},         // Yellow
    etl: {start: '#ff6b35', end: '#f72585', stroke: '#ff6b35'},        // Orange-Pink
};

class LatticeGraph {
    constructor(container) {
        this.container = container;
        this.svg = null;
        this.simulation = null;
        this.nodes = [];
        this.edges = [];
        this.selectedNode = null;
        this.width = 0;
        this.height = 0;

        // Execution state
        this.executionState = {
            isRunning: false,
            assetStatuses: new Map(),
            ws: null,
            memoryTimeline: [],
            peakRss: 0,
            currentPartitionDate: null,
            currentPartitionIndex: 0,
            totalPartitions: 0,
        };

        // Date selection state
        this.dateState = {
            mode: 'single', // 'single' or 'range'
            startDate: null,
            endDate: null,
        };

        this.init();
    }

    async init() {
        this.setupSVG();
        this.setupZoom();
        this.setupDefs();
        await this.loadData();
        this.render();
        this.setupEventListeners();
        this.setupExecutionUI();
        this.hideLoading();
    }

    setupSVG() {
        const container = document.getElementById(this.container);
        this.width = container.clientWidth;
        this.height = container.clientHeight;

        this.svg = d3.select(`#${this.container} svg`)
            .attr('width', this.width)
            .attr('height', this.height);

        this.g = this.svg.append('g');
    }

    setupZoom() {
        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                this.g.attr('transform', event.transform);
            });

        this.svg.call(zoom);

        // Initial zoom to center
        const initialTransform = d3.zoomIdentity
            .translate(this.width / 2, this.height / 2)
            .scale(0.8);
        this.svg.call(zoom.transform, initialTransform);
    }

    setupDefs() {
        const defs = this.svg.append('defs');

        // Arrow marker
        defs.append('marker')
            .attr('id', 'arrow')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 20)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-5L10,0L0,5')
            .attr('class', 'edge-arrow');

        defs.append('marker')
            .attr('id', 'arrow-highlighted')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 20)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-5L10,0L0,5')
            .attr('class', 'edge-arrow highlighted');

        // Gradients for each group
        Object.entries(GROUP_COLORS).forEach(([group, colors]) => {
            const gradient = defs.append('linearGradient')
                .attr('id', `gradient-${group}`)
                .attr('x1', '0%')
                .attr('y1', '0%')
                .attr('x2', '100%')
                .attr('y2', '100%');

            gradient.append('stop')
                .attr('offset', '0%')
                .attr('stop-color', colors.start);

            gradient.append('stop')
                .attr('offset', '100%')
                .attr('stop-color', colors.end);
        });
    }

    async loadData() {
        try {
            const response = await fetch('/api/graph');
            const data = await response.json();

            this.nodes = data.nodes.map(n => ({...n}));
            this.edges = data.edges.map(e => ({...e}));

            // Update asset count
            document.getElementById('asset-count').textContent = String(this.nodes.length).padStart(3, '0');

        } catch (error) {
            console.error('Failed to load graph data:', error);
            document.getElementById('asset-count').textContent = 'ERR';
        }
    }

    render() {
        // Create edges
        this.edgeElements = this.g.append('g')
            .attr('class', 'edges')
            .selectAll('path')
            .data(this.edges)
            .join('path')
            .attr('class', 'edge')
            .attr('marker-end', 'url(#arrow)');

        // Create nodes
        this.nodeElements = this.g.append('g')
            .attr('class', 'nodes')
            .selectAll('g')
            .data(this.nodes)
            .join('g')
            .attr('class', 'node')
            .call(this.drag());

        // Node rectangles with neon glow
        this.nodeElements.append('rect')
            .attr('width', 130)
            .attr('height', 44)
            .attr('x', -65)
            .attr('y', -22)
            .attr('rx', 4)
            .attr('class', d => `group-${d.group}`)
            .style('fill', d => {
                return `url(#gradient-${d.group in GROUP_COLORS ? d.group : 'default'})`;
            })
            .style('stroke', d => {
                const colors = GROUP_COLORS[d.group] || GROUP_COLORS.default;
                return colors.stroke;
            })
            .style('filter', d => {
                const colors = GROUP_COLORS[d.group] || GROUP_COLORS.default;
                return `drop-shadow(0 0 8px ${colors.stroke}66)`;
            });

        // Node labels
        this.nodeElements.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '0.35em')
            .text(d => d.name.length > 16 ? d.name.slice(0, 14) + '...' : d.name);

        // Compute hierarchical layout (left-to-right)
        this.computeHierarchicalLayout();

        // Setup simulation with fixed positions
        this.simulation = d3.forceSimulation(this.nodes)
            .force('link', d3.forceLink(this.edges)
                .id(d => d.id)
                .distance(150))
            .on('tick', () => this.tick())
            .on('end', () => this.lockAllNodes());

        // Lock nodes immediately since we computed positions
        this.lockAllNodes();
        this.simulation.stop();
        this.tick();
    }

    computeHierarchicalLayout() {
        const nodeMap = new Map(this.nodes.map(n => [n.id, n]));

        // Build adjacency list (what each node depends on)
        const dependencies = new Map();
        const dependents = new Map();

        this.nodes.forEach(n => {
            dependencies.set(n.id, []);
            dependents.set(n.id, []);
        });

        this.edges.forEach(e => {
            const sourceId = typeof e.source === 'object' ? e.source.id : e.source;
            const targetId = typeof e.target === 'object' ? e.target.id : e.target;
            dependencies.get(targetId).push(sourceId);
            dependents.get(sourceId).push(targetId);
        });

        // Compute level for each node (longest path from any source)
        const levels = new Map();

        const computeLevel = (nodeId, visited = new Set()) => {
            if (levels.has(nodeId)) return levels.get(nodeId);
            if (visited.has(nodeId)) return 0; // Cycle protection

            visited.add(nodeId);
            const deps = dependencies.get(nodeId) || [];

            if (deps.length === 0) {
                levels.set(nodeId, 0);
                return 0;
            }

            const maxDepLevel = Math.max(...deps.map(d => computeLevel(d, visited)));
            const level = maxDepLevel + 1;
            levels.set(nodeId, level);
            return level;
        };

        this.nodes.forEach(n => computeLevel(n.id));

        // Group nodes by level
        const levelGroups = new Map();
        this.nodes.forEach(n => {
            const level = levels.get(n.id);
            if (!levelGroups.has(level)) levelGroups.set(level, []);
            levelGroups.get(level).push(n);
        });

        // Sort levels
        const sortedLevels = Array.from(levelGroups.keys()).sort((a, b) => a - b);
        const maxLevel = sortedLevels[sortedLevels.length - 1] || 0;

        // Layout parameters
        const horizontalSpacing = 200;
        const verticalSpacing = 80;
        const startX = -((maxLevel * horizontalSpacing) / 2);

        // Position nodes
        sortedLevels.forEach(level => {
            const nodesAtLevel = levelGroups.get(level);
            const levelHeight = nodesAtLevel.length * verticalSpacing;
            const startY = -levelHeight / 2 + verticalSpacing / 2;

            nodesAtLevel.forEach((node, index) => {
                node.x = startX + level * horizontalSpacing;
                node.y = startY + index * verticalSpacing;
                node.fx = node.x;
                node.fy = node.y;
            });
        });
    }

    tick() {
        this.edgeElements.attr('d', d => {
            const dx = d.target.x - d.source.x;
            const dy = d.target.y - d.source.y;
            return `M${d.source.x},${d.source.y}L${d.target.x},${d.target.y}`;
        });

        this.nodeElements.attr('transform', d => `translate(${d.x},${d.y})`);
    }

    drag() {
        return d3.drag()
            .on('start', (event, d) => {
                if (!event.active) this.simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on('drag', (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on('end', (event, d) => {
                if (!event.active) this.simulation.alphaTarget(0);
                // Keep node locked in place after dragging
                // d.fx and d.fy remain set
            });
    }

    lockAllNodes() {
        this.nodes.forEach(d => {
            d.fx = d.x;
            d.fy = d.y;
        });
    }

    unlockAllNodes() {
        // Recompute hierarchical layout
        this.computeHierarchicalLayout();
        this.tick();
    }

    setupEventListeners() {
        const tooltip = document.getElementById('tooltip');
        const sidebar = document.getElementById('sidebar');
        const closeSidebar = document.getElementById('close-sidebar');

        // Node hover
        this.nodeElements
            .on('mouseenter', (event, d) => {
                tooltip.innerHTML = `
                    <div class="font-display font-bold" style="color: #05d9e8; text-shadow: 0 0 10px rgba(5,217,232,0.5);">${d.name}</div>
                    <div style="color: #8888aa; font-size: 0.7rem; letter-spacing: 0.1em; margin-top: 4px;">${d.group.toUpperCase()}</div>
                    ${d.return_type ? `<div style="color: #ff2a6d; font-size: 0.75rem; margin-top: 6px; font-family: 'Space Mono', monospace;">${d.return_type}</div>` : ''}
                `;
                tooltip.style.opacity = '1';
                this.highlightConnections(d);
            })
            .on('mousemove', (event) => {
                tooltip.style.left = `${event.pageX + 10}px`;
                tooltip.style.top = `${event.pageY + 10}px`;
            })
            .on('mouseleave', () => {
                tooltip.style.opacity = '0';
                this.clearHighlights();
            })
            .on('click', async (event, d) => {
                event.stopPropagation();
                await this.selectNode(d);
            });

        // Close sidebar
        closeSidebar.addEventListener('click', () => {
            sidebar.classList.add('translate-x-full');
            this.selectedNode = null;
            this.nodeElements.classed('selected', false);
        });

        // Click outside to deselect
        this.svg.on('click', () => {
            sidebar.classList.add('translate-x-full');
            this.selectedNode = null;
            this.nodeElements.classed('selected', false);
        });

        // Theme toggle
        document.getElementById('theme-toggle').addEventListener('click', () => {
            const html = document.documentElement;
            const isCurrentlyDark = html.classList.contains('dark');

            if (isCurrentlyDark) {
                html.classList.remove('dark');
                html.classList.add('light');
            } else {
                html.classList.remove('light');
                html.classList.add('dark');
            }

            // Toggle sun/moon icons
            document.querySelector('#theme-toggle .sun').classList.toggle('hidden');
            document.querySelector('#theme-toggle .moon').classList.toggle('hidden');
        });

        // Relayout button
        document.getElementById('relayout-btn').addEventListener('click', () => {
            this.unlockAllNodes();
        });

        // Window resize
        window.addEventListener('resize', () => {
            this.width = document.getElementById(this.container).clientWidth;
            this.height = document.getElementById(this.container).clientHeight;
            this.svg.attr('width', this.width).attr('height', this.height);
        });
    }

    highlightConnections(node) {
        const connectedIds = new Set();

        this.edges.forEach(e => {
            if (e.source.id === node.id) connectedIds.add(e.target.id);
            if (e.target.id === node.id) connectedIds.add(e.source.id);
        });

        this.edgeElements
            .classed('highlighted', e =>
                e.source.id === node.id || e.target.id === node.id)
            .attr('marker-end', e =>
                (e.source.id === node.id || e.target.id === node.id)
                    ? 'url(#arrow-highlighted)'
                    : 'url(#arrow)');

        this.nodeElements
            .style('opacity', d =>
                d.id === node.id || connectedIds.has(d.id) ? 1 : 0.3);
    }

    clearHighlights() {
        this.edgeElements
            .classed('highlighted', false)
            .attr('marker-end', 'url(#arrow)');
        this.nodeElements.style('opacity', 1);
    }

    async selectNode(node) {
        const sidebar = document.getElementById('sidebar');
        const content = document.getElementById('sidebar-content');

        this.selectedNode = node;
        this.nodeElements.classed('selected', d => d.id === node.id);

        // Show loading state
        content.innerHTML = '<div style="color: #05d9e8; font-family: Orbitron, sans-serif; letter-spacing: 0.2em; animation: textFlicker 1.5s ease-in-out infinite;">LOADING...</div>';
        sidebar.classList.remove('translate-x-full');

        try {
            const response = await fetch(`/api/assets/${encodeURIComponent(node.id)}`);
            const data = await response.json();

            content.innerHTML = `
                <div class="detail-section">
                    <div class="detail-label">Name</div>
                    <div class="detail-value font-display" style="font-size: 1.25rem; color: #05d9e8; text-shadow: 0 0 15px rgba(5,217,232,0.5);">${data.name}</div>
                </div>

                <div class="detail-section">
                    <div class="detail-label">Group</div>
                    <div class="detail-value" style="letter-spacing: 0.1em;">${data.group.toUpperCase()}</div>
                </div>

                ${data.return_type ? `
                <div class="detail-section">
                    <div class="detail-label">Return Type</div>
                    <div class="detail-value" style="color: #f6ff00; text-shadow: 0 0 10px rgba(246,255,0,0.4);">${data.return_type}</div>
                </div>
                ` : ''}

                ${data.description ? `
                <div class="detail-section">
                    <div class="detail-label">Description</div>
                    <div class="detail-value" style="color: #8888aa; line-height: 1.6;">${data.description}</div>
                </div>
                ` : ''}

                <div class="detail-section">
                    <div class="detail-label">Dependencies (${data.dependencies.length})</div>
                    <div class="dep-list">
                        ${data.dependencies.length > 0
                ? data.dependencies.map(d => `<span class="dep-badge" data-asset="${d}">${d}</span>`).join('')
                : '<span style="color: #4a4a6a; font-size: 0.85rem;">[ NONE ]</span>'}
                    </div>
                </div>

                <div class="detail-section">
                    <div class="detail-label">Dependents (${data.dependents.length})</div>
                    <div class="dep-list">
                        ${data.dependents.length > 0
                ? data.dependents.map(d => `<span class="dep-badge" data-asset="${d}">${d}</span>`).join('')
                : '<span style="color: #4a4a6a; font-size: 0.85rem;">[ NONE ]</span>'}
                    </div>
                </div>

            `;

            // Add click handlers for dependency badges
            content.querySelectorAll('.dep-badge').forEach(badge => {
                badge.addEventListener('click', () => {
                    const assetId = badge.dataset.asset;
                    const targetNode = this.nodes.find(n => n.id === assetId);
                    if (targetNode) this.selectNode(targetNode);
                });
            });

        } catch (error) {
            content.innerHTML = `<div style="color: #ff2a6d; font-family: Orbitron, sans-serif; letter-spacing: 0.1em;">ERROR: ASSET DATA UNAVAILABLE</div>`;
        }
    }

    hideLoading() {
        document.getElementById('loading').style.display = 'none';
    }

    // === Execution UI Methods ===

    setupExecutionUI() {
        // Create execute button with date selection panel
        const controls = document.createElement('div');
        controls.className = 'execution-controls';
        controls.innerHTML = `
            <div class="date-selection-panel" id="date-selection-panel">
                <div class="date-panel-header">// PARTITION DATE</div>
                <div class="date-mode-toggle">
                    <button class="date-mode-btn active" data-mode="single">SINGLE</button>
                    <button class="date-mode-btn" data-mode="range">RANGE</button>
                </div>
                <div class="date-single-input" id="date-single-input">
                    <div class="date-input-group">
                        <label class="date-input-label">EXECUTION DATE</label>
                        <input type="date" class="date-input" id="execution-date">
                    </div>
                </div>
                <div class="date-range-inputs" id="date-range-inputs">
                    <div class="date-input-group">
                        <label class="date-input-label">START DATE</label>
                        <input type="date" class="date-input" id="execution-date-start">
                    </div>
                    <div class="date-input-group">
                        <label class="date-input-label">END DATE</label>
                        <input type="date" class="date-input" id="execution-date-end">
                    </div>
                </div>
                <div class="date-preview" id="date-preview" style="display: none;"></div>
            </div>
            <button id="execute-btn" class="execute-btn">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span>EXECUTE</span>
            </button>
        `;
        document.body.appendChild(controls);

        // Setup date selection event listeners
        this.setupDateSelectionListeners();

        // Create memory panel
        const memoryPanel = document.createElement('div');
        memoryPanel.id = 'memory-panel';
        memoryPanel.className = 'memory-panel hidden';
        memoryPanel.innerHTML = `
            <div class="memory-panel-header">
                <span class="memory-panel-title">// MEMORY USAGE</span>
            </div>
            <div class="memory-stat">
                <span class="memory-stat-label">CURRENT RSS</span>
                <span id="current-rss" class="memory-stat-value">-- MB</span>
            </div>
            <div class="memory-stat">
                <span class="memory-stat-label">PEAK RSS</span>
                <span id="peak-rss" class="memory-stat-value peak">-- MB</span>
            </div>
            <div class="memory-sparkline">
                <svg viewBox="0 0 100 40" preserveAspectRatio="none">
                    <defs>
                        <linearGradient id="sparkline-gradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stop-color="#05d9e8" stop-opacity="0.6"/>
                            <stop offset="100%" stop-color="#05d9e8" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <path id="sparkline-area" class="memory-sparkline-area"/>
                    <path id="sparkline-path" class="memory-sparkline-path"/>
                </svg>
            </div>
        `;
        document.body.appendChild(memoryPanel);

        // Create progress indicator
        const progress = document.createElement('div');
        progress.id = 'execution-progress';
        progress.className = 'execution-progress hidden';
        progress.innerHTML = `
            <div class="execution-progress-spinner"></div>
            <span class="execution-progress-text">EXECUTING:</span>
            <span id="progress-current-asset" class="execution-progress-count" style="margin: 0 8px;">---</span>
            <span class="execution-progress-text">[</span>
            <span id="progress-current" class="execution-progress-count">0</span>
            <span class="execution-progress-text">/</span>
            <span id="progress-total" class="execution-progress-count">${this.nodes.length}</span>
            <span class="execution-progress-text">]</span>
        `;
        document.body.appendChild(progress);

        // Event listener for execute button
        document.getElementById('execute-btn').addEventListener('click', () => this.startExecution());
    }

    setupDateSelectionListeners() {
        // Mode toggle buttons
        document.querySelectorAll('.date-mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.date-mode-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                const mode = btn.dataset.mode;
                this.dateState.mode = mode;

                const singleInput = document.getElementById('date-single-input');
                const rangeInputs = document.getElementById('date-range-inputs');

                if (mode === 'single') {
                    singleInput.classList.remove('hidden');
                    rangeInputs.classList.remove('active');
                } else {
                    singleInput.classList.add('hidden');
                    rangeInputs.classList.add('active');
                }

                this.updateDatePreview();
            });
        });

        // Date input changes
        document.getElementById('execution-date').addEventListener('change', (e) => {
            this.dateState.startDate = e.target.value || null;
            this.updateDatePreview();
        });

        document.getElementById('execution-date-start').addEventListener('change', (e) => {
            this.dateState.startDate = e.target.value || null;
            this.updateDatePreview();
        });

        document.getElementById('execution-date-end').addEventListener('change', (e) => {
            this.dateState.endDate = e.target.value || null;
            this.updateDatePreview();
        });
    }

    updateDatePreview() {
        const preview = document.getElementById('date-preview');

        if (this.dateState.mode === 'single') {
            if (this.dateState.startDate) {
                preview.style.display = 'block';
                preview.classList.remove('range');
                preview.textContent = `> ${this.dateState.startDate}`;
            } else {
                preview.style.display = 'none';
            }
        } else {
            if (this.dateState.startDate && this.dateState.endDate) {
                const start = new Date(this.dateState.startDate);
                const end = new Date(this.dateState.endDate);
                const dayCount = Math.floor((end - start) / (1000 * 60 * 60 * 24)) + 1;

                if (dayCount > 0) {
                    preview.style.display = 'block';
                    preview.classList.add('range');
                    preview.textContent = `> ${this.dateState.startDate} to ${this.dateState.endDate} (${dayCount} day${dayCount !== 1 ? 's' : ''})`;
                } else {
                    preview.style.display = 'block';
                    preview.classList.add('range');
                    preview.textContent = `> Invalid range`;
                }
            } else if (this.dateState.startDate || this.dateState.endDate) {
                preview.style.display = 'block';
                preview.classList.add('range');
                preview.textContent = `> Select both dates`;
            } else {
                preview.style.display = 'none';
            }
        }
    }

    async startExecution() {
        if (this.executionState.isRunning) return;

        const btn = document.getElementById('execute-btn');
        btn.disabled = true;
        btn.classList.add('running');
        btn.querySelector('span').textContent = 'CONNECTING...';

        // Show UI elements
        document.getElementById('memory-panel').classList.remove('hidden');
        document.getElementById('execution-progress').classList.remove('hidden');

        // Reset state
        this.executionState.isRunning = true;
        this.executionState.assetStatuses.clear();
        this.executionState.memoryTimeline = [];
        this.executionState.peakRss = 0;
        this.executionState.currentPartitionDate = null;
        this.executionState.currentPartitionIndex = 0;
        this.executionState.totalPartitions = 0;

        // Reset node visual states
        this.nodeElements.attr('class', 'node');

        // Reset progress display
        document.getElementById('progress-current').textContent = '0';
        document.getElementById('progress-total').textContent = this.nodes.length;
        const currentAssetEl = document.getElementById('progress-current-asset');
        if (currentAssetEl) {
            currentAssetEl.textContent = 'STARTING...';
            currentAssetEl.style.color = '';  // Reset to default CSS color
        }
        document.getElementById('current-rss').textContent = '-- MB';
        document.getElementById('peak-rss').textContent = '-- MB';

        // Connect WebSocket and wait for it to be ready
        try {
            await this.connectExecutionWebSocket();
            btn.querySelector('span').textContent = 'RUNNING...';

            // Build request body with date parameters
            const requestBody = {};

            if (this.dateState.mode === 'single' && this.dateState.startDate) {
                requestBody.execution_date = this.dateState.startDate;
            } else if (this.dateState.mode === 'range' && this.dateState.startDate && this.dateState.endDate) {
                requestBody.execution_date = this.dateState.startDate;
                requestBody.execution_date_end = this.dateState.endDate;
            }

            // Start execution after WebSocket is connected
            const response = await fetch('/api/execution/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(requestBody),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start execution');
            }

        } catch (error) {
            console.error('Execution failed:', error);
            this.stopExecution();
        }
    }

    connectExecutionWebSocket() {
        return new Promise((resolve, reject) => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(`${protocol}//${window.location.host}/ws/execution`);

            ws.onopen = () => {
                console.log('WebSocket connected');
                resolve();
            };

            ws.onmessage = (event) => {
                const message = JSON.parse(event.data);
                console.log('WebSocket message:', message);
                this.handleWebSocketMessage(message);
            };

            ws.onclose = () => {
                console.log('WebSocket closed');
                if (this.executionState.isRunning) {
                    // Reconnect if still running
                    setTimeout(() => this.connectExecutionWebSocket(), 1000);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(error);
            };

            this.executionState.ws = ws;
        });
    }

    handleWebSocketMessage(message) {
        switch (message.type) {
            case 'asset_start':
                this.updateAssetStatus(message.data.asset_id, 'running');
                break;

            case 'asset_complete':
                this.updateAssetStatus(message.data.asset_id, message.data.status);
                break;

            case 'memory_update':
                this.updateMemoryDisplay(message.data);
                break;

            case 'partition_start':
                this.handlePartitionStart(message.data);
                break;

            case 'partition_complete':
                this.handlePartitionComplete(message.data);
                break;

            case 'execution_complete':
                this.showExecutionComplete(message.data);
                this.stopExecution();
                break;
        }
    }

    handlePartitionStart(data) {
        this.executionState.currentPartitionDate = data.current_date;
        this.executionState.currentPartitionIndex = data.current_date_index;
        this.executionState.totalPartitions = data.total_dates;

        // Reset node visual states for new partition
        this.nodeElements.attr('class', 'node');
        this.executionState.assetStatuses.clear();

        // Update progress display with partition info
        const currentAssetEl = document.getElementById('progress-current-asset');
        if (currentAssetEl) {
            currentAssetEl.textContent = `[${data.current_date_index}/${data.total_dates}] ${data.current_date}`;
            currentAssetEl.style.color = '';
        }

        // Reset progress counter for this partition
        document.getElementById('progress-current').textContent = '0';
    }

    handlePartitionComplete(data) {
        console.log('Partition complete:', data);
        // Partition completion is logged, the UI will show the next partition_start or execution_complete
    }

    showExecutionComplete(data) {
        const currentAssetEl = document.getElementById('progress-current-asset');
        if (currentAssetEl) {
            if (data.failed_count > 0) {
                currentAssetEl.textContent = 'FAILED';
                currentAssetEl.style.color = '#ff2a6d';
            } else {
                currentAssetEl.textContent = 'COMPLETE';
                currentAssetEl.style.color = '#05d9e8';
            }
        }
        // Update total count with actual executed count
        const total = data.completed_count + data.failed_count;
        document.getElementById('progress-total').textContent = total;
        document.getElementById('progress-current').textContent = total;
    }

    updateAssetStatus(assetId, status) {
        this.executionState.assetStatuses.set(assetId, status);

        const node = this.nodeElements.filter(d => d.id === assetId);

        // Update node class
        node.attr('class', `node status-${status}`);

        // Update current asset display when running
        if (status === 'running') {
            const currentAssetEl = document.getElementById('progress-current-asset');
            if (currentAssetEl) {
                const displayName = assetId.includes('/') ? assetId.split('/').pop() : assetId;
                currentAssetEl.textContent = displayName.toUpperCase();
            }
        }

        // Update progress counter
        const completed = [...this.executionState.assetStatuses.values()]
            .filter(s => s === 'completed' || s === 'failed').length;
        document.getElementById('progress-current').textContent = completed;
    }

    updateMemoryDisplay(data) {
        const rssMb = data.rss_mb.toFixed(1);
        document.getElementById('current-rss').textContent = `${rssMb} MB`;

        if (data.rss_mb > this.executionState.peakRss) {
            this.executionState.peakRss = data.rss_mb;
            document.getElementById('peak-rss').textContent = `${rssMb} MB`;
        }

        // Update sparkline
        this.executionState.memoryTimeline.push(data.rss_mb);
        if (this.executionState.memoryTimeline.length > 100) {
            this.executionState.memoryTimeline.shift();
        }
        this.updateSparkline();
    }

    updateSparkline() {
        const data = this.executionState.memoryTimeline;
        if (data.length < 2) return;

        const max = Math.max(...data) * 1.1;
        const min = Math.min(...data) * 0.9;
        const range = max - min || 1;

        const points = data.map((v, i) => {
            const x = (i / (data.length - 1)) * 100;
            const y = 40 - ((v - min) / range) * 35;
            return `${x},${y}`;
        });

        const pathD = `M${points.join(' L')}`;
        const areaD = `M0,40 L${points.join(' L')} L100,40 Z`;

        document.getElementById('sparkline-path').setAttribute('d', pathD);
        document.getElementById('sparkline-area').setAttribute('d', areaD);
    }

    stopExecution() {
        this.executionState.isRunning = false;

        if (this.executionState.ws) {
            this.executionState.ws.close();
            this.executionState.ws = null;
        }

        const btn = document.getElementById('execute-btn');
        const controlsContainer = document.querySelector('.execution-controls');
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('running');
            btn.querySelector('span').textContent = 'EXECUTE';
        }
        document.getElementById('execution-progress').classList.add('hidden');

        // Keep memory panel visible for a bit to see final stats
        setTimeout(() => {
            if (!this.executionState.isRunning) {
                document.getElementById('memory-panel').classList.add('hidden');
            }
        }, 5000);
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    new LatticeGraph('graph-container');
});
