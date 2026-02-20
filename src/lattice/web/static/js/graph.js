/**
 * Lattice Graph Visualization
 * D3.js force-directed graph with interactive features
 */

// Muted mission control palette for asset groups
const GROUP_COLORS = {
    default: {start: '#8068a8', end: '#2e2048', stroke: '#9680b8'},    // Brighter Purple
    analytics: {start: '#68b5c2', end: '#24545e', stroke: '#7ec8d4'},  // Brighter Teal
    data: {start: '#c45270', end: '#6e2038', stroke: '#d46a86'},       // Brighter Rose
    ml: {start: '#d0b454', end: '#6e5c20', stroke: '#dcc468'},         // Brighter Amber
    etl: {start: '#cf7a56', end: '#6e3420', stroke: '#d99070'},        // Brighter Coral
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

        // === EDGE GRADIENTS ===
        // Main edge gradient: dusty purple to muted teal
        const edgeGradient = defs.append('linearGradient')
            .attr('id', 'edge-gradient')
            .attr('gradientUnits', 'userSpaceOnUse');
        edgeGradient.append('stop')
            .attr('offset', '0%')
            .attr('stop-color', '#8068a8');
        edgeGradient.append('stop')
            .attr('offset', '50%')
            .attr('stop-color', '#9680b8');
        edgeGradient.append('stop')
            .attr('offset', '100%')
            .attr('stop-color', '#68b5c2');

        // Highlighted edge gradient: dusty rose to muted teal
        const edgeGradientHighlight = defs.append('linearGradient')
            .attr('id', 'edge-gradient-highlight')
            .attr('gradientUnits', 'userSpaceOnUse');
        edgeGradientHighlight.append('stop')
            .attr('offset', '0%')
            .attr('stop-color', '#c45270');
        edgeGradientHighlight.append('stop')
            .attr('offset', '100%')
            .attr('stop-color', '#68b5c2');

        // === GLOW FILTERS ===
        // Edge glow filter
        const edgeGlow = defs.append('filter')
            .attr('id', 'edge-glow')
            .attr('x', '-50%')
            .attr('y', '-50%')
            .attr('width', '200%')
            .attr('height', '200%');
        edgeGlow.append('feGaussianBlur')
            .attr('in', 'SourceGraphic')
            .attr('stdDeviation', '3')
            .attr('result', 'blur');
        edgeGlow.append('feMerge')
            .html('<feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/>');

        // Intense glow for highlighted edges
        const edgeGlowIntense = defs.append('filter')
            .attr('id', 'edge-glow-intense')
            .attr('x', '-100%')
            .attr('y', '-100%')
            .attr('width', '300%')
            .attr('height', '300%');
        edgeGlowIntense.append('feGaussianBlur')
            .attr('in', 'SourceGraphic')
            .attr('stdDeviation', '6')
            .attr('result', 'blur');
        edgeGlowIntense.append('feMerge')
            .html('<feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/>');

        // === ARROW MARKERS ===
        // Futuristic angular arrow - default
        const arrow = defs.append('marker')
            .attr('id', 'arrow')
            .attr('viewBox', '0 -6 14 12')
            .attr('refX', 12)
            .attr('refY', 0)
            .attr('markerWidth', 10)
            .attr('markerHeight', 10)
            .attr('orient', 'auto');
        // Diamond/chevron shape for futuristic feel
        arrow.append('path')
            .attr('d', 'M0,-5 L4,0 L0,5 L12,0 Z')
            .attr('fill', '#68b5c2')
            .attr('filter', 'drop-shadow(0 0 2px rgba(104,181,194,0.4))');

        // Highlighted arrow
        const arrowHighlight = defs.append('marker')
            .attr('id', 'arrow-highlighted')
            .attr('viewBox', '0 -6 14 12')
            .attr('refX', 12)
            .attr('refY', 0)
            .attr('markerWidth', 12)
            .attr('markerHeight', 12)
            .attr('orient', 'auto');
        arrowHighlight.append('path')
            .attr('d', 'M0,-5 L4,0 L0,5 L12,0 Z')
            .attr('fill', '#68b5c2')
            .attr('filter', 'drop-shadow(0 0 3px rgba(104,181,194,0.5))');

        // === NODE GRADIENTS ===
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
        // Create edge groups (each edge has multiple layers for glow effect)
        const edgeGroups = this.g.append('g')
            .attr('class', 'edges')
            .selectAll('g')
            .data(this.edges)
            .join('g')
            .attr('class', 'edge-group');

        // Layer 1: Subtle glow layer (wider, soft)
        edgeGroups.append('path')
            .attr('class', 'edge-glow-layer')
            .attr('fill', 'none')
            .attr('stroke', 'url(#edge-gradient)')
            .attr('stroke-width', 4)
            .attr('opacity', 0.2)
            .attr('filter', 'url(#edge-glow)');

        // Layer 2: Main edge with gradient
        edgeGroups.append('path')
            .attr('class', 'edge-main')
            .attr('fill', 'none')
            .attr('stroke', 'url(#edge-gradient)')
            .attr('stroke-width', 2);

        // Store reference to edge groups for tick updates
        this.edgeGroups = edgeGroups;
        this.edgeElements = edgeGroups.selectAll('.edge-main');

        // Create nodes
        this.nodeElements = this.g.append('g')
            .attr('class', 'nodes')
            .selectAll('g')
            .data(this.nodes)
            .join('g')
            .attr('class', 'node')
            .call(this.drag());

        // Node labels (render first to measure text width)
        this.nodeElements.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '0.35em')
            .text(d => d.name);

        // Measure each label and store width on datum
        const MIN_NODE_WIDTH = 130;
        const NODE_PADDING = 28; // horizontal padding around text
        this.nodeElements.each(function(d) {
            const textEl = d3.select(this).select('text').node();
            const textWidth = textEl.getComputedTextLength();
            d._nodeWidth = Math.max(MIN_NODE_WIDTH, textWidth + NODE_PADDING);
        });

        // Node rectangles with neon glow (sized to fit text)
        this.nodeElements.insert('rect', 'text')
            .attr('width', d => d._nodeWidth)
            .attr('height', 44)
            .attr('x', d => -d._nodeWidth / 2)
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

        // Check slivers on the right side of node (full height, stacked horizontally)
        this.nodeElements.each(function(d) {
            const node = d3.select(this);
            const checks = d.checks || [];
            if (checks.length === 0) return;

            // Muted teal variations for multiple checks
            const cyanShades = [
                '#68b5c2', // Base brighter teal
                '#5ca0ac', // Slightly darker
                '#508e9a', // More muted
                '#457c88', // Deep teal
                '#78c2ce', // Lighter teal
            ];

            // Calculate sliver dimensions
            const sliverWidth = 4;
            const sliverGap = 1;
            const sliverHeight = 44; // Full height of asset block
            const halfWidth = d._nodeWidth / 2;
            const startX = halfWidth + 2; // Position to right of main rect

            checks.forEach((check, i) => {
                const color = cyanShades[i % cyanShades.length];
                node.append('rect')
                    .attr('class', 'check-sliver')
                    .attr('width', sliverWidth)
                    .attr('height', sliverHeight)
                    .attr('x', startX + i * (sliverWidth + sliverGap))
                    .attr('y', -22) // Same y as main rect
                    .attr('rx', 1)
                    .style('fill', color)
                    .style('filter', `drop-shadow(0 0 4px ${color}cc)`)
                    .append('title')
                    .text(check.name);
            });
        });

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
        // Generate curved path for an edge
        const generatePath = (d) => {
            // Per-node widths
            const sourceHalfWidth = (d.source._nodeWidth || 130) / 2;
            const targetHalfWidth = (d.target._nodeWidth || 130) / 2;

            // Calculate check sliver offset for source node (right side)
            const sourceChecks = d.source.checks ? d.source.checks.length : 0;
            const sliverOffset = sourceChecks > 0 ? (sourceChecks * 5) + 2 : 0;

            // Source: right edge (plus slivers), Target: left edge
            const sourceX = d.source.x + sourceHalfWidth + sliverOffset;
            const targetX = d.target.x - targetHalfWidth;
            const sourceY = d.source.y;
            const targetY = d.target.y;

            // Calculate control points for smooth bezier curve
            const dx = targetX - sourceX;
            const dy = targetY - sourceY;

            // Control point offset (creates smooth S-curve or gentle arc)
            const curvature = Math.min(Math.abs(dx) * 0.3, 60);

            // Use quadratic bezier for smoother, more elegant curves
            const midX = sourceX + dx * 0.5;
            const midY = sourceY + dy * 0.5;

            // If nodes are mostly horizontal, create gentle arc
            // If there's vertical offset, create S-curve
            if (Math.abs(dy) < 30) {
                // Gentle arc
                const controlY = midY - Math.sign(dy || 1) * curvature * 0.3;
                return `M${sourceX},${sourceY} Q${midX},${controlY} ${targetX},${targetY}`;
            } else {
                // S-curve with two control points
                const c1x = sourceX + curvature;
                const c1y = sourceY;
                const c2x = targetX - curvature;
                const c2y = targetY;
                return `M${sourceX},${sourceY} C${c1x},${c1y} ${c2x},${c2y} ${targetX},${targetY}`;
            }
        };

        // Update gradient positions to follow edge direction
        this.edgeGroups.each(function(d) {
            // Update all path layers with the same curved path
            const path = generatePath(d);
            d3.select(this).selectAll('path').attr('d', path);
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
                    <div class="font-display font-bold" style="color: #68b5c2;">${d.name}</div>
                    <div style="color: #8282a0; font-size: 0.7rem; letter-spacing: 0.1em; margin-top: 4px;">${d.group.toUpperCase()}</div>
                    ${d.return_type ? `<div style="color: #c45270; font-size: 0.75rem; margin-top: 6px; font-family: 'Space Mono', monospace;">${d.return_type}</div>` : ''}
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
            .on('click', (event, d) => {
                if (event.defaultPrevented) return; // Ignore drag-end clicks (D3 pattern)
                event.stopPropagation();
                this.handleNodeClick(d);
            });

        // Close sidebar
        closeSidebar.addEventListener('click', () => {
            this.deselectNode();
        });

        // Click outside to deselect
        this.svg.on('click', () => {
            this.deselectNode();
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

        // Escape key deselects current node
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.selectedNode) {
                this.deselectNode();
            }
        });
    }

    highlightConnections(node) {
        const connectedIds = new Set();

        this.edges.forEach(e => {
            if (e.source.id === node.id) connectedIds.add(e.target.id);
            if (e.target.id === node.id) connectedIds.add(e.source.id);
        });

        // Highlight edge groups
        this.edgeGroups.each(function(e) {
            const isConnected = e.source.id === node.id || e.target.id === node.id;
            const group = d3.select(this);

            group.classed('highlighted', isConnected);

            // Update glow layer
            group.select('.edge-glow-layer')
                .attr('stroke', isConnected ? 'url(#edge-gradient-highlight)' : 'url(#edge-gradient)')
                .attr('stroke-width', isConnected ? 8 : 4)
                .attr('opacity', isConnected ? 0.4 : 0.2)
                .attr('filter', isConnected ? 'url(#edge-glow-intense)' : 'url(#edge-glow)');

            // Update main edge
            group.select('.edge-main')
                .attr('stroke', isConnected ? 'url(#edge-gradient-highlight)' : 'url(#edge-gradient)')
                .attr('stroke-width', isConnected ? 2.5 : 2);
        });

        this.nodeElements
            .style('opacity', d =>
                d.id === node.id || connectedIds.has(d.id) ? 1 : 0.3);
    }

    clearHighlights() {
        this.edgeGroups.each(function() {
            const group = d3.select(this);
            group.classed('highlighted', false);

            group.select('.edge-glow-layer')
                .attr('stroke', 'url(#edge-gradient)')
                .attr('stroke-width', 4)
                .attr('opacity', 0.2)
                .attr('filter', 'url(#edge-glow)');

            group.select('.edge-main')
                .attr('stroke', 'url(#edge-gradient)')
                .attr('stroke-width', 2);
        });

        this.nodeElements.style('opacity', 1);
    }

    async selectNode(node) {
        const sidebar = document.getElementById('sidebar');
        const content = document.getElementById('sidebar-content');

        this.selectedNode = node;
        this.nodeElements.classed('selected', d => d.id === node.id);

        // Show loading state
        content.innerHTML = '<div style="color: #68b5c2; font-family: Orbitron, sans-serif; letter-spacing: 0.2em; animation: textFlicker 1.5s ease-in-out infinite;">LOADING...</div>';
        sidebar.classList.remove('translate-x-full');

        // Move execution controls out of the way
        const execControls = document.querySelector('.execution-controls');
        if (execControls) execControls.classList.add('sidebar-open');
        const memPanel = document.getElementById('memory-panel');
        if (memPanel) memPanel.classList.add('sidebar-open');

        try {
            const response = await fetch(`/api/assets/${encodeURIComponent(node.id)}`);
            const data = await response.json();

            content.innerHTML = `
                <div class="detail-section">
                    <div class="detail-label">Name</div>
                    <div class="detail-value font-display" style="font-size: 1.25rem; color: #68b5c2;">${data.name}</div>
                </div>

                <div class="detail-section">
                    <div class="detail-label">Group</div>
                    <div class="detail-value" style="letter-spacing: 0.1em;">${data.group.toUpperCase()}</div>
                </div>

                ${data.return_type ? `
                <div class="detail-section">
                    <div class="detail-label">Return Type</div>
                    <div class="detail-value" style="color: #d0b454;">${data.return_type}</div>
                </div>
                ` : ''}

                ${data.description ? `
                <div class="detail-section">
                    <div class="detail-label">Description</div>
                    <div class="detail-value" style="color: #8282a0; line-height: 1.6;">${data.description}</div>
                </div>
                ` : ''}

                <div class="detail-section">
                    <div class="detail-label">Checks (${data.checks ? data.checks.length : 0})</div>
                    <div class="check-list">
                        ${data.checks && data.checks.length > 0
                ? data.checks.map(c => `
                    <div class="check-badge">
                        <span class="check-badge-icon">✓</span>
                        <span class="check-badge-name">${c.name}</span>
                        ${c.description ? `<span class="check-badge-desc">${c.description}</span>` : ''}
                    </div>
                `).join('')
                : '<span style="color: #5a5a72; font-size: 0.85rem;">[ NO CHECKS ]</span>'}
                    </div>
                </div>

                <div class="detail-section">
                    <div class="detail-label">Dependencies (${data.dependencies.length})</div>
                    <div class="dep-list">
                        ${data.dependencies.length > 0
                ? data.dependencies.map(d => `<span class="dep-badge" data-asset="${d}">${d}</span>`).join('')
                : '<span style="color: #5a5a72; font-size: 0.85rem;">[ NONE ]</span>'}
                    </div>
                </div>

                <div class="detail-section">
                    <div class="detail-label">Dependents (${data.dependents.length})</div>
                    <div class="dep-list">
                        ${data.dependents.length > 0
                ? data.dependents.map(d => `<span class="dep-badge" data-asset="${d}">${d}</span>`).join('')
                : '<span style="color: #5a5a72; font-size: 0.85rem;">[ NONE ]</span>'}
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
            content.innerHTML = `<div style="color: #c45270; font-family: Orbitron, sans-serif; letter-spacing: 0.1em;">ERROR: ASSET DATA UNAVAILABLE</div>`;
        }
    }

    handleNodeClick(d) {
        // Toggle selection: clicking the already-selected node deselects it
        if (this.selectedNode && this.selectedNode.id === d.id) {
            this.deselectNode();
            return;
        }
        this.selectNodeForExecution(d);
    }

    selectNodeForExecution(d) {
        this.selectedNode = d;

        // Highlight selected node visually
        this.nodeElements.classed('selected', n => n.id === d.id);

        // Update execute button label
        this.updateExecuteButtonLabel();
    }

    deselectNode() {
        this.selectedNode = null;
        this.nodeElements.classed('selected', false);
        this.updateExecuteButtonLabel();

        // Close right sidebar and remove sidebar-open from execution controls
        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.classList.add('translate-x-full');
        const execControls = document.querySelector('.execution-controls');
        if (execControls) execControls.classList.remove('sidebar-open');
        const memPanel = document.getElementById('memory-panel');
        if (memPanel) memPanel.classList.remove('sidebar-open');
    }

    updateExecuteButtonLabel() {
        const btn = document.getElementById('execute-btn');
        if (!btn) return;
        const span = btn.querySelector('span');
        if (!span) return;

        if (this.selectedNode) {
            const name = this.selectedNode.name || this.selectedNode.id;
            const status = this.executionState.assetStatuses.get(this.selectedNode.id);

            if (status === 'failed') {
                span.textContent = `RE-EXECUTE FROM ${name.toUpperCase()}`;
            } else {
                span.textContent = `EXECUTE FROM ${name.toUpperCase()}`;
            }
        } else {
            span.textContent = 'EXECUTE';
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

        // Re-apply selected class if a node is selected (class reset clears it)
        if (this.selectedNode) {
            this.nodeElements.classed('selected', n => n.id === this.selectedNode.id);
        }

        // Reset progress display
        document.getElementById('progress-current').textContent = '0';
        document.getElementById('progress-total').textContent = this.selectedNode ? '...' : this.nodes.length;
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

            // Targeted execution when a node is selected
            if (this.selectedNode) {
                requestBody.target = this.selectedNode.id;
                requestBody.include_downstream = true;
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
                currentAssetEl.style.color = '#c45270';
            } else {
                currentAssetEl.textContent = 'COMPLETE';
                currentAssetEl.style.color = '#68b5c2';
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

        // Update execute button label if selected node status changed
        if (this.selectedNode && this.selectedNode.id === assetId) {
            this.updateExecuteButtonLabel();
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
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('running');
        }

        // Clear selection and reset button label
        this.deselectNode();
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
