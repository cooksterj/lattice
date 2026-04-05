/**
 * Lattice Overview Graph Visualization
 * Renders a meta-graph on the main page showing named groups as large
 * super-nodes and standalone (default-group) assets as regular nodes,
 * with edges illustrating the dependency connections between them.
 */

const GROUP_COLORS = {
    default: {start: '#8068a8', end: '#2e2048', stroke: '#9680b8'},
    analytics: {start: '#68b5c2', end: '#24545e', stroke: '#7ec8d4'},
    data: {start: '#c45270', end: '#6e2038', stroke: '#d46a86'},
    ml: {start: '#d0b454', end: '#6e5c20', stroke: '#dcc468'},
    etl: {start: '#cf7a56', end: '#6e3420', stroke: '#d99070'},
    dbt: {start: '#e87d3e', end: '#7a3a14', stroke: '#f0954e'},
    jaffle_shop: {start: '#e87d3e', end: '#7a3a14', stroke: '#f0954e'},
};

const EXECUTION_TYPE_ICONS = {
    dbt:    'ov-icon-dbt',
    python: 'ov-icon-python',
    shell:  'ov-icon-shell',
};

class OverviewGraph {
    constructor(containerId) {
        this.container = containerId;
        this.svg = null;
        this.zoom = null;
        this.nodes = [];
        this.edges = [];
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
            mode: 'single',
            startDate: null,
            endDate: null,
        };

        // Total asset count (fetched from /health for progress display)
        this.totalAssetCount = 0;

        // Map asset ID (e.g. "analytics/stats") → overview node ID (e.g. "group:analytics")
        this.assetToNodeId = new Map();
        // Track per-group asset statuses for aggregate group-node status
        this.groupAssetStatuses = new Map();

        // Drag state (suppresses tooltips while dragging)
        this._isDragging = false;

        // SPA navigation state
        this.currentView = 'overview';
        this.currentGroupName = null;
        this.overviewNodes = [];
        this.overviewEdges = [];
        this.groupViewData = null;
        this.stubNodeElements = null;
        this.externalEdgeGroups = null;
        this._fullGraphNodes = null;

        this.init();
    }

    async init() {
        this.setupSVG();
        this.setupZoom();
        this.setupDefs();
        await this.loadData();

        // Save overview data for re-rendering after group view
        this.overviewNodes = this.nodes.map(n => ({...n}));
        this.overviewEdges = this.edges.map(e => ({...e}));

        if (this.nodes.length > 0) {
            this.render();
            this.setupOverviewNodeInteractions();
            this.applyEntranceAnimations();
        }
        this.setupEventListeners();
        this.setupNavigation();
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
        this.zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => {
                this.g.attr('transform', event.transform);
            });

        this.svg.call(this.zoom);
    }

    setupDefs() {
        const defs = this.svg.append('defs');

        // Edge gradient
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

        const edgeGradientHighlight = defs.append('linearGradient')
            .attr('id', 'edge-gradient-highlight')
            .attr('gradientUnits', 'userSpaceOnUse');
        edgeGradientHighlight.append('stop')
            .attr('offset', '0%')
            .attr('stop-color', '#c45270');
        edgeGradientHighlight.append('stop')
            .attr('offset', '100%')
            .attr('stop-color', '#68b5c2');

        // Glow filters
        const edgeGlow = defs.append('filter')
            .attr('id', 'edge-glow')
            .attr('x', '-50%').attr('y', '-50%')
            .attr('width', '200%').attr('height', '200%');
        edgeGlow.append('feGaussianBlur')
            .attr('in', 'SourceGraphic')
            .attr('stdDeviation', '3')
            .attr('result', 'blur');
        edgeGlow.append('feMerge')
            .html('<feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/>');

        const edgeGlowIntense = defs.append('filter')
            .attr('id', 'edge-glow-intense')
            .attr('x', '-100%').attr('y', '-100%')
            .attr('width', '300%').attr('height', '300%');
        edgeGlowIntense.append('feGaussianBlur')
            .attr('in', 'SourceGraphic')
            .attr('stdDeviation', '6')
            .attr('result', 'blur');
        edgeGlowIntense.append('feMerge')
            .html('<feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/>');

        // Arrow marker
        const arrow = defs.append('marker')
            .attr('id', 'arrow')
            .attr('viewBox', '0 -6 14 12')
            .attr('refX', 12).attr('refY', 0)
            .attr('markerWidth', 10).attr('markerHeight', 10)
            .attr('orient', 'auto');
        arrow.append('path')
            .attr('d', 'M0,-5 L4,0 L0,5 L12,0 Z')
            .attr('fill', '#68b5c2')
            .attr('filter', 'drop-shadow(0 0 2px rgba(104,181,194,0.4))');

        const arrowHighlight = defs.append('marker')
            .attr('id', 'arrow-highlighted')
            .attr('viewBox', '0 -6 14 12')
            .attr('refX', 12).attr('refY', 0)
            .attr('markerWidth', 12).attr('markerHeight', 12)
            .attr('orient', 'auto');
        arrowHighlight.append('path')
            .attr('d', 'M0,-5 L4,0 L0,5 L12,0 Z')
            .attr('fill', '#68b5c2')
            .attr('filter', 'drop-shadow(0 0 3px rgba(104,181,194,0.5))');

        // === EXECUTION TYPE ICON SYMBOLS ===
        const dbtSymbol = defs.append('symbol')
            .attr('id', 'ov-icon-dbt')
            .attr('viewBox', '0 0 24 24');
        dbtSymbol.append('path')
            .attr('fill', '#e87d3e')
            .attr('d', 'M17.9 9.38a8.15 8.15 0 0 0-3.04-3.12l1.77.84a10.29 10.29 0 0 1 3.74 3l3.23-5.93a2.85 2.85 0 0 0-.06-2.96 2.86 2.86 0 0 0-3.57-.86l-5.87 3.21a4.36 4.36 0 0 1-4.18 0L4.18.41a2.85 2.85 0 0 0-2.96.06A2.86 2.86 0 0 0 .35 3.97l3.2 5.94a4.36 4.36 0 0 1 0 4.18l-3.13 5.74a2.86 2.86 0 0 0 .09 3 2.86 2.86 0 0 0 3.54.84l6.06-3.3a10.29 10.29 0 0 1-3-3.75l-.84-1.77a8.15 8.15 0 0 0 3.12 3.04l10.58 5.78a2.86 2.86 0 0 0 3.54-.84 2.87 2.87 0 0 0 .08-3L17.9 9.38zm3.38-7.74a1.09 1.09 0 1 1 0 2.18 1.09 1.09 0 0 1 0-2.18zM2.74 3.82a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18zm0 18.54a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18zm10.36-11.45a2.17 2.17 0 0 0-2.18 2.17c0 .62.26 1.2.7 1.61a2.72 2.72 0 1 1 3.07-4.48 2.16 2.16 0 0 0-1.6-.7v.4zm8.18 11.45a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18z');

        const pySymbol = defs.append('symbol')
            .attr('id', 'ov-icon-python')
            .attr('viewBox', '0 0 24 24');
        pySymbol.append('path')
            .attr('fill', '#68b5c2')
            .attr('d', 'M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.21.02H8.77l-.69.05-.59.14-.5.22-.41.27-.33.32-.27.35-.2.36-.15.37-.1.35-.07.32-.04.27-.02.21v3.06H3.17l-.21-.03-.28-.07-.32-.12-.35-.18-.36-.26-.36-.36-.35-.46-.32-.59-.28-.73-.21-.88-.14-1.05-.05-1.23.06-1.22.16-1.04.24-.87.32-.71.36-.57.4-.44.42-.33.42-.24.4-.16.36-.1.32-.05.24-.01h.16l.06.01h8.16v-.83H6.18l-.01-2.75-.02-.37.05-.34.11-.31.17-.28.25-.26.31-.23.38-.2.44-.18.51-.15.58-.12.64-.1.71-.06.77-.04.84-.02 1.27.05zm-6.3 1.98l-.23.33-.08.41.08.41.23.34.33.22.41.09.41-.09.33-.22.23-.34.08-.41-.08-.41-.23-.33-.33-.22-.41-.09-.41.09zm13.09 3.95l.28.06.32.12.35.18.36.27.36.35.35.47.32.59.28.73.21.88.14 1.04.05 1.23-.06 1.23-.16 1.04-.24.86-.32.71-.36.57-.4.45-.42.33-.42.24-.4.16-.36.09-.32.05-.24.02-.16-.01h-8.22v.82h5.84l.01 2.76.02.36-.05.34-.11.31-.17.29-.25.25-.31.24-.38.2-.44.17-.51.15-.58.13-.64.09-.71.07-.77.04-.84.01-1.27-.04-1.07-.14-.9-.2-.73-.25-.59-.3-.45-.33-.34-.34-.25-.34-.16-.33-.1-.3-.04-.25-.02-.2.01-.13v-5.34l.05-.64.13-.54.21-.46.26-.38.3-.32.33-.24.35-.2.35-.14.33-.1.3-.06.26-.04.21-.02.13-.01h5.84l.69-.05.59-.14.5-.21.41-.28.33-.32.27-.35.2-.36.15-.36.1-.35.07-.32.04-.28.02-.21V6.07h2.09l.14.01zm-6.47 14.25l-.23.33-.08.41.08.41.23.33.33.23.41.08.41-.08.33-.23.23-.33.08-.41-.08-.41-.23-.33-.33-.23-.41-.08-.41.08z');

        const shellSymbol = defs.append('symbol')
            .attr('id', 'ov-icon-shell')
            .attr('viewBox', '0 0 24 24');
        shellSymbol.append('path')
            .attr('fill', 'none')
            .attr('stroke', '#9680b8')
            .attr('stroke-width', 2.5)
            .attr('stroke-linecap', 'round')
            .attr('stroke-linejoin', 'round')
            .attr('d', 'M4 17l6-5-6-5');
        shellSymbol.append('path')
            .attr('fill', 'none')
            .attr('stroke', '#9680b8')
            .attr('stroke-width', 2.5)
            .attr('stroke-linecap', 'round')
            .attr('d', 'M12 19h8');

        // Node gradients
        Object.entries(GROUP_COLORS).forEach(([group, colors]) => {
            const gradient = defs.append('linearGradient')
                .attr('id', `gradient-${group}`)
                .attr('x1', '0%').attr('y1', '0%')
                .attr('x2', '100%').attr('y2', '100%');
            gradient.append('stop')
                .attr('offset', '0%')
                .attr('stop-color', colors.start);
            gradient.append('stop')
                .attr('offset', '100%')
                .attr('stop-color', colors.end);
        });

        // Stub node gradient (used in group detail view)
        const stubGradient = defs.append('linearGradient')
            .attr('id', 'gradient-stub')
            .attr('x1', '0%').attr('y1', '0%')
            .attr('x2', '100%').attr('y2', '100%');
        stubGradient.append('stop')
            .attr('offset', '0%')
            .attr('stop-color', '#5a5a6e');
        stubGradient.append('stop')
            .attr('offset', '100%')
            .attr('stop-color', '#2e2e3e');

        // External edge arrow marker (muted, for group detail view)
        const arrowExternal = defs.append('marker')
            .attr('id', 'arrow-external')
            .attr('viewBox', '0 -6 14 12')
            .attr('refX', 12).attr('refY', 0)
            .attr('markerWidth', 8).attr('markerHeight', 8)
            .attr('orient', 'auto');
        arrowExternal.append('path')
            .attr('d', 'M0,-5 L4,0 L0,5 L12,0 Z')
            .attr('fill', '#6a6a80')
            .attr('opacity', 0.5);
    }

    async loadData() {
        try {
            const [overviewResponse, healthResponse, graphResponse] = await Promise.all([
                fetch('/api/assets/overview'),
                fetch('/health'),
                fetch('/api/graph'),
            ]);

            if (!overviewResponse.ok) throw new Error(`HTTP ${overviewResponse.status}`);
            const data = await overviewResponse.json();

            this.nodes = data.nodes.map(n => ({...n}));
            this.edges = data.edges.map(e => ({...e}));

            if (healthResponse.ok) {
                const healthData = await healthResponse.json();
                this.totalAssetCount = healthData.asset_count || 0;
            }

            // Build asset ID → overview node ID mapping from full graph data
            if (graphResponse.ok) {
                const graphData = await graphResponse.json();
                this._fullGraphNodes = graphData.nodes;
                for (const asset of graphData.nodes) {
                    // asset.id is like "source_data" or "analytics/stats"
                    // asset.group is like "default" or "analytics"
                    if (asset.group === 'default') {
                        this.assetToNodeId.set(asset.id, asset.id);
                    } else {
                        this.assetToNodeId.set(asset.id, `group:${asset.group}`);
                    }
                }
            }

            // Update count display
            const countEl = document.getElementById('overview-count');
            if (countEl) {
                const groups = this.nodes.filter(n => n.node_type === 'group').length;
                const assets = this.nodes.filter(n => n.node_type === 'asset').length;
                const parts = [];
                if (groups > 0) parts.push(`${groups} GROUP${groups !== 1 ? 'S' : ''}`);
                if (assets > 0) parts.push(`${assets} ASSET${assets !== 1 ? 'S' : ''}`);
                countEl.textContent = parts.join(' + ') || '0';
            }
        } catch (error) {
            console.error('Failed to load overview graph:', error);
            const countEl = document.getElementById('overview-count');
            if (countEl) countEl.textContent = 'ERR';
        }
    }

    render() {
        this.computeHierarchicalLayout();
        this.renderEdges();
        this.renderNodes();
        this.updateEdgePaths();
        this.fitToContent();
    }

    computeHierarchicalLayout() {
        const nodeMap = new Map(this.nodes.map(n => [n.id, n]));

        const dependencies = new Map();
        const dependents = new Map();

        this.nodes.forEach(n => {
            dependencies.set(n.id, []);
            dependents.set(n.id, []);
        });

        this.edges.forEach(e => {
            const sourceId = typeof e.source === 'object' ? e.source.id : e.source;
            const targetId = typeof e.target === 'object' ? e.target.id : e.target;
            if (dependencies.has(targetId)) dependencies.get(targetId).push(sourceId);
            if (dependents.has(sourceId)) dependents.get(sourceId).push(targetId);
        });

        const levels = new Map();

        const computeLevel = (nodeId, visited = new Set()) => {
            if (levels.has(nodeId)) return levels.get(nodeId);
            if (visited.has(nodeId)) return 0;

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

        const levelGroups = new Map();
        this.nodes.forEach(n => {
            const level = levels.get(n.id);
            if (!levelGroups.has(level)) levelGroups.set(level, []);
            levelGroups.get(level).push(n);
        });

        const sortedLevels = Array.from(levelGroups.keys()).sort((a, b) => a - b);
        const maxLevel = sortedLevels[sortedLevels.length - 1] || 0;

        const horizontalSpacing = 220;
        const verticalSpacing = 90;
        const startX = -((maxLevel * horizontalSpacing) / 2);

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

    renderEdges() {
        const edgeGroups = this.g.append('g')
            .attr('class', 'edges')
            .selectAll('g')
            .data(this.edges)
            .join('g')
            .attr('class', 'edge-group');

        // Glow layer
        edgeGroups.append('path')
            .attr('class', 'edge-glow-layer')
            .attr('fill', 'none')
            .attr('stroke', 'url(#edge-gradient)')
            .attr('stroke-width', 4)
            .attr('opacity', 0.2)
            .attr('filter', 'url(#edge-glow)');

        // Main edge
        edgeGroups.append('path')
            .attr('class', 'edge-main')
            .attr('fill', 'none')
            .attr('stroke', 'url(#edge-gradient)')
            .attr('stroke-width', 2);

        this.edgeGroups = edgeGroups;
    }

    renderNodes() {
        const nodeGroups = this.g.append('g')
            .attr('class', 'nodes')
            .selectAll('g')
            .data(this.nodes)
            .join('g')
            .attr('class', d => `node node-${d.node_type}`)
            .call(this.drag());

        const MIN_NODE_WIDTH = 130;
        const NODE_HEIGHT = 44;
        const NODE_PADDING = 28;

        // Format group names for display (e.g. "jaffle_shop" → "Jaffle Shop")
        const formatLabel = (d) => {
            if (d.node_type === 'group') {
                return d.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            }
            return d.name;
        };

        // Add text labels first to measure widths
        nodeGroups.each(function(d) {
            const node = d3.select(this);

            // Single-line label for both groups and assets
            node.append('text')
                .attr('text-anchor', 'middle')
                .attr('dy', '0.35em')
                .text(formatLabel(d));

            const textWidth = node.select('text').node().getComputedTextLength();
            d._nodeWidth = Math.max(MIN_NODE_WIDTH, textWidth + NODE_PADDING);
            d._nodeHeight = NODE_HEIGHT;
        });

        // Insert rects behind text
        nodeGroups.insert('rect', 'text')
            .attr('width', d => d._nodeWidth)
            .attr('height', d => d._nodeHeight)
            .attr('x', d => -d._nodeWidth / 2)
            .attr('y', d => -d._nodeHeight / 2)
            .attr('rx', 4)
            .style('fill', d => {
                const group = d.node_type === 'group' ? d.group : 'default';
                return `url(#gradient-${group in GROUP_COLORS ? group : 'default'})`;
            })
            .style('stroke', d => {
                const group = d.node_type === 'group' ? d.group : 'default';
                const colors = GROUP_COLORS[group] || GROUP_COLORS.default;
                return colors.stroke;
            })
            .style('filter', d => {
                const group = d.node_type === 'group' ? d.group : 'default';
                const colors = GROUP_COLORS[group] || GROUP_COLORS.default;
                return `drop-shadow(0 0 8px ${colors.stroke}66)`;
            });

        // Execution type icons (bottom-right corner, asset nodes only)
        nodeGroups.each(function(d) {
            if (d.node_type !== 'asset') return;
            const symbolId = EXECUTION_TYPE_ICONS[d.execution_type];
            if (!symbolId) return;

            const node = d3.select(this);
            const halfWidth = d._nodeWidth / 2;
            const iconSize = 12;
            const padding = 3;

            node.append('use')
                .attr('class', 'exec-type-icon')
                .attr('href', `#${symbolId}`)
                .attr('width', iconSize)
                .attr('height', iconSize)
                .attr('x', halfWidth - iconSize - padding)
                .attr('y', NODE_HEIGHT / 2 - iconSize - padding)
                .style('opacity', 0.85);
        });

        // Check slivers on the right side of node (stacked horizontally)
        const cyanShades = [
            '#68b5c2', '#5ca0ac', '#508e9a', '#457c88', '#78c2ce',
        ];

        nodeGroups.each(function(d) {
            const count = d.check_count || 0;
            if (count === 0) return;

            // Groups get a single indicator; standalone assets get per-check slivers
            const displayCount = d.node_type === 'group' ? 1 : count;

            const node = d3.select(this);
            const sliverWidth = 4;
            const sliverGap = 1;
            const sliverHeight = NODE_HEIGHT;
            const halfWidth = d._nodeWidth / 2;
            const startX = halfWidth + 2;

            for (let i = 0; i < displayCount; i++) {
                const color = cyanShades[i % cyanShades.length];
                node.append('rect')
                    .attr('class', 'check-sliver')
                    .attr('width', sliverWidth)
                    .attr('height', sliverHeight)
                    .attr('x', startX + i * (sliverWidth + sliverGap))
                    .attr('y', -NODE_HEIGHT / 2)
                    .attr('rx', 1)
                    .style('fill', color)
                    .style('filter', `drop-shadow(0 0 4px ${color}cc)`);
            }
        });

        // Position nodes
        nodeGroups.attr('transform', d => `translate(${d.x},${d.y})`);

        this.nodeElements = nodeGroups;
    }

    updateEdgePaths() {
        const nodeMap = new Map(this.nodes.map(n => [n.id, n]));

        this.edgeGroups.each(function(edge) {
            const sourceNode = nodeMap.get(typeof edge.source === 'object' ? edge.source.id : edge.source);
            const targetNode = nodeMap.get(typeof edge.target === 'object' ? edge.target.id : edge.target);

            if (!sourceNode || !targetNode) return;

            const sourceHalfW = (sourceNode._nodeWidth || 130) / 2;
            const targetHalfW = (targetNode._nodeWidth || 130) / 2;

            // Offset for check slivers on source node
            // Groups show a single sliver; standalone assets show per-check slivers
            const sourceChecks = sourceNode.check_count || 0;
            const displayChecks = sourceNode.node_type === 'group' ? Math.min(sourceChecks, 1) : sourceChecks;
            const sliverOffset = displayChecks > 0 ? (displayChecks * 5) + 2 : 0;

            const sx = sourceNode.x + sourceHalfW + sliverOffset;
            const sy = sourceNode.y;
            const tx = targetNode.x - targetHalfW;
            const ty = targetNode.y;

            const dx = tx - sx;
            const dy = ty - sy;
            const curvature = Math.min(Math.abs(dx) * 0.3, 60);

            let path;
            if (Math.abs(dy) < 30) {
                const midX = sx + dx * 0.5;
                const midY = sy + dy * 0.5;
                const controlY = midY - Math.sign(dy || 1) * curvature * 0.3;
                path = `M${sx},${sy} Q${midX},${controlY} ${tx},${ty}`;
            } else {
                const c1x = sx + curvature;
                const c1y = sy;
                const c2x = tx - curvature;
                const c2y = ty;
                path = `M${sx},${sy} C${c1x},${c1y} ${c2x},${c2y} ${tx},${ty}`;
            }

            d3.select(this).selectAll('path').attr('d', path);
        });
    }

    fitToContent() {
        if (this.nodes.length === 0) return;

        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        this.nodes.forEach(n => {
            const halfW = (n._nodeWidth || 130) / 2;
            const halfH = (n._nodeHeight || 44) / 2;
            if (n.x - halfW < minX) minX = n.x - halfW;
            if (n.x + halfW > maxX) maxX = n.x + halfW;
            if (n.y - halfH < minY) minY = n.y - halfH;
            if (n.y + halfH > maxY) maxY = n.y + halfH;
        });

        const contentWidth = maxX - minX;
        const contentHeight = maxY - minY;
        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;

        const headerHeight = 64;
        const padding = 60;
        const availableWidth = this.width - padding * 2;
        const availableHeight = this.height - headerHeight - padding;

        if (availableWidth <= 0 || availableHeight <= 0) return;

        const scaleX = availableWidth / contentWidth;
        const scaleY = availableHeight / contentHeight;
        const scale = Math.min(scaleX, scaleY, 1.5);

        const tx = this.width / 2 - centerX * scale;
        const ty = headerHeight + availableHeight / 2 - centerY * scale + padding / 2;

        const transform = d3.zoomIdentity.translate(tx, ty).scale(scale);
        this.svg.call(this.zoom.transform, transform);
    }

    drag() {
        let draggedEl = null;

        return d3.drag()
            .on('start', (event, d) => {
                d._dragged = false;
                d.fx = d.x;
                d.fy = d.y;
                // Capture the node <g> element once — event.sourceEvent.target
                // shifts to whatever is under the cursor during subsequent moves.
                draggedEl = event.sourceEvent.target.closest('.node');
            })
            .on('drag', (event, d) => {
                if (!d._dragged) {
                    this._isDragging = true;
                    const tooltip = document.getElementById('tooltip');
                    if (tooltip) tooltip.style.opacity = '0';
                }
                d._dragged = true;
                d.fx = event.x;
                d.fy = event.y;
                d.x = event.x;
                d.y = event.y;

                // Move the node visually using the captured element
                if (draggedEl) {
                    d3.select(draggedEl)
                        .attr('transform', `translate(${d.x},${d.y})`);
                }

                // Recompute edge paths for the active view
                if (this.currentView === 'group') {
                    this._updateGroupEdgePaths();
                } else {
                    this.updateEdgePaths();
                }
            })
            .on('end', () => {
                draggedEl = null;
                this._isDragging = false;
            });
    }

    setupOverviewNodeInteractions() {
        if (!this.nodeElements) return;

        const tooltip = document.getElementById('tooltip');

        this.nodeElements
            .on('mouseenter', (event, d) => {
                if (this._isDragging) return;
                if (d.node_type === 'group') {
                    const colors = GROUP_COLORS[d.group] || GROUP_COLORS.default;
                    const displayName = d.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                    const checkLine = d.check_count > 0
                        ? `<div style="color: #68b5c2; font-size: 0.75rem; font-family: 'Orbitron', sans-serif;">${d.check_count} CHECK${d.check_count !== 1 ? 'S' : ''}</div>`
                        : '';
                    tooltip.innerHTML = `
                        <div class="font-display font-bold" style="color: ${colors.stroke};">${displayName.toUpperCase()}</div>
                        <div style="color: #8282a0; font-size: 0.7rem; letter-spacing: 0.1em; margin-top: 4px;">GROUP</div>
                        <div style="color: #68b5c2; font-size: 0.75rem; margin-top: 6px; font-family: 'Orbitron', sans-serif;">${d.asset_count} ASSET${d.asset_count !== 1 ? 'S' : ''}</div>
                        ${checkLine}
                        <div style="color: #8282a0; font-size: 0.65rem; margin-top: 4px;">Click to explore</div>
                    `;
                } else {
                    const checkLine = d.check_count > 0
                        ? `<div style="color: #68b5c2; font-size: 0.7rem; margin-top: 4px; font-family: 'Orbitron', sans-serif;">${d.check_count} CHECK${d.check_count !== 1 ? 'S' : ''}</div>`
                        : '';
                    tooltip.innerHTML = `
                        <div class="font-display font-bold" style="color: #9680b8;">${d.name}</div>
                        <div style="color: #8282a0; font-size: 0.7rem; letter-spacing: 0.1em; margin-top: 4px;">STANDALONE ASSET</div>
                        ${checkLine}
                    `;
                }
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
                if (event.defaultPrevented) return;
                if (d._dragged) {
                    d._dragged = false;
                    return;
                }
                event.stopPropagation();

                if (d.node_type === 'group') {
                    this.transitionToGroup(d.group);
                } else {
                    window.location.href = '/asset/' + encodeURIComponent(d.id);
                }
            });
    }

    setupEventListeners() {
        // Relayout button
        const relayoutBtn = document.getElementById('relayout-btn');
        if (relayoutBtn) {
            relayoutBtn.addEventListener('click', () => {
                this.fitToContent();
            });
        }

        // Theme toggle
        const themeToggle = document.getElementById('theme-toggle');
        const html = document.documentElement;

        function updateThemeIcons() {
            const isDark = html.classList.contains('dark');
            themeToggle.querySelector('.sun').classList.toggle('hidden', isDark);
            themeToggle.querySelector('.moon').classList.toggle('hidden', !isDark);
        }

        themeToggle.addEventListener('click', () => {
            html.classList.toggle('dark');
            html.classList.toggle('light');
            localStorage.setItem('theme', html.classList.contains('dark') ? 'dark' : 'light');
            updateThemeIcons();
        });

        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'light') {
            html.classList.remove('dark');
            html.classList.add('light');
        }
        updateThemeIcons();

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
            const srcId = typeof e.source === 'object' ? e.source.id : e.source;
            const tgtId = typeof e.target === 'object' ? e.target.id : e.target;
            if (srcId === node.id) connectedIds.add(tgtId);
            if (tgtId === node.id) connectedIds.add(srcId);
        });

        // Highlight edges
        this.edgeGroups.each(function(e) {
            const srcId = typeof e.source === 'object' ? e.source.id : e.source;
            const tgtId = typeof e.target === 'object' ? e.target.id : e.target;
            const isConnected = srcId === node.id || tgtId === node.id;
            const group = d3.select(this);

            group.select('.edge-glow-layer')
                .attr('stroke', isConnected ? 'url(#edge-gradient-highlight)' : 'url(#edge-gradient)')
                .attr('stroke-width', isConnected ? 8 : 4)
                .attr('opacity', isConnected ? 0.4 : 0.2)
                .attr('filter', isConnected ? 'url(#edge-glow-intense)' : 'url(#edge-glow)');

            group.select('.edge-main')
                .attr('stroke', isConnected ? 'url(#edge-gradient-highlight)' : 'url(#edge-gradient)')
                .attr('stroke-width', isConnected ? 2.5 : 2);
        });

        // Dim unconnected nodes
        this.nodeElements
            .style('opacity', d =>
                d.id === node.id || connectedIds.has(d.id) ? 1 : 0.3);
    }

    clearHighlights() {
        this.edgeGroups.each(function() {
            const group = d3.select(this);
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

    hideLoading() {
        const loadingEl = document.getElementById('loading');
        if (loadingEl) {
            loadingEl.style.display = 'none';
        }
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
            <span id="progress-total" class="execution-progress-count">${this.totalAssetCount}</span>
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
        this.groupAssetStatuses.clear();

        // Reset node visual states
        if (this.nodeElements) {
            this.nodeElements.attr('class', d => `node node-${d.node_type}`);
        }

        // Reset progress display
        document.getElementById('progress-current').textContent = '0';
        document.getElementById('progress-total').textContent = this.totalAssetCount;
        const currentAssetEl = document.getElementById('progress-current-asset');
        if (currentAssetEl) {
            currentAssetEl.textContent = 'STARTING...';
            currentAssetEl.style.color = '';
        }
        document.getElementById('current-rss').textContent = '-- MB';
        document.getElementById('peak-rss').textContent = '-- MB';

        // Connect WebSocket and wait for it to be ready
        try {
            await this.connectExecutionWebSocket();
            btn.querySelector('span').textContent = 'RUNNING...';

            // Build request body with date parameters (no target — always full pipeline)
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

        // Reset asset statuses for new partition
        this.executionState.assetStatuses.clear();
        this.groupAssetStatuses.clear();

        // Reset node visual states
        if (this.nodeElements) {
            this.nodeElements.attr('class', d => `node node-${d.node_type}`);
        }

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
        const total = data.completed_count + data.failed_count;
        document.getElementById('progress-total').textContent = total;
        document.getElementById('progress-current').textContent = total;
    }

    updateAssetStatus(assetId, status) {
        this.executionState.assetStatuses.set(assetId, status);

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

        // Update node visuals
        const nodeId = this.assetToNodeId.get(assetId);
        if (!nodeId || !this.nodeElements) return;

        if (nodeId.startsWith('group:')) {
            // Track per-asset status within this group
            if (!this.groupAssetStatuses.has(nodeId)) {
                this.groupAssetStatuses.set(nodeId, new Map());
            }
            this.groupAssetStatuses.get(nodeId).set(assetId, status);

            // Derive aggregate status — only mark completed when ALL group assets are done
            const statuses = [...this.groupAssetStatuses.get(nodeId).values()];
            const groupNode = this.nodes.find(n => n.id === nodeId);
            const totalAssets = groupNode ? groupNode.asset_count : statuses.length;
            const terminalCount = statuses.filter(s => s === 'completed' || s === 'failed').length;

            let groupStatus;
            if (statuses.includes('running')) {
                groupStatus = 'running';
            } else if (terminalCount < totalAssets) {
                // Some assets haven't started yet — group is still in progress
                groupStatus = 'running';
            } else if (statuses.includes('failed')) {
                groupStatus = 'failed';
            } else {
                groupStatus = 'completed';
            }

            this.nodeElements
                .filter(d => d.id === nodeId)
                .attr('class', `node node-group status-${groupStatus}`);
        } else {
            // Standalone asset node — apply status directly
            this.nodeElements
                .filter(d => d.id === nodeId)
                .attr('class', `node node-asset status-${status}`);
        }
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
            btn.querySelector('span').textContent = 'EXECUTE';
        }

        document.getElementById('execution-progress').classList.add('hidden');

        // Reset node visuals after a delay (keep final status visible briefly)
        setTimeout(() => {
            if (!this.executionState.isRunning && this.nodeElements) {
                if (this.currentView === 'overview') {
                    this.nodeElements.attr('class', d => `node node-${d.node_type}`);
                } else {
                    this.nodeElements.attr('class', 'node');
                }
                this.groupAssetStatuses.clear();
            }
        }, 5000);

        // Keep memory panel visible for a bit to see final stats
        setTimeout(() => {
            if (!this.executionState.isRunning) {
                document.getElementById('memory-panel').classList.add('hidden');
            }
        }, 5000);
    }

    // ================================================================
    //  SPA NAVIGATION — Overview ↔ Group Detail
    // ================================================================

    setupNavigation() {
        history.replaceState({ view: 'overview' }, '', window.location.pathname);

        window.addEventListener('popstate', (event) => {
            if (event.state && event.state.view === 'group') {
                this._navigateToGroup(event.state.group);
            } else {
                this._navigateToOverview();
            }
        });
    }

    async transitionToGroup(groupName) {
        history.pushState(
            { view: 'group', group: groupName },
            '',
            '/group/' + encodeURIComponent(groupName),
        );
        await this._navigateToGroup(groupName);
    }

    async _navigateToGroup(groupName) {
        this.currentView = 'group';
        this.currentGroupName = groupName;

        const displayName = groupName.replace(/_/g, ' ').toUpperCase();
        const subtitle = document.getElementById('page-subtitle');
        if (subtitle) subtitle.textContent = `GROUP // ${displayName}`;

        await this._fadeOutView();

        try {
            const response = await fetch(
                `/api/groups/${encodeURIComponent(groupName)}/graph`,
            );
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            this.groupViewData = await response.json();
        } catch (error) {
            console.error('Failed to load group graph:', error);
            return;
        }

        this._renderGroupView(this.groupViewData);
        this._rebuildGroupAssetNodeMapping(this.groupViewData);
        this.applyEntranceAnimations();
    }

    async _navigateToOverview() {
        this.currentView = 'overview';
        this.currentGroupName = null;

        const subtitle = document.getElementById('page-subtitle');
        if (subtitle) subtitle.textContent = 'ASSET GROUPS';

        await this._fadeOutView();

        // Restore overview data and re-render
        this.nodes = this.overviewNodes.map(n => ({...n}));
        this.edges = this.overviewEdges.map(e => ({...e}));
        this.render();
        this.setupOverviewNodeInteractions();
        this._rebuildOverviewAssetNodeMapping();
        this._updateOverviewCount();
        this.applyEntranceAnimations();
    }

    async _fadeOutView() {
        this.g.selectAll('*').remove();
        this.nodeElements = null;
        this.edgeGroups = null;
        this.stubNodeElements = null;
        this.externalEdgeGroups = null;
    }

    _updateOverviewCount() {
        const countEl = document.getElementById('overview-count');
        if (!countEl) return;
        const groups = this.nodes.filter(n => n.node_type === 'group').length;
        const assets = this.nodes.filter(n => n.node_type === 'asset').length;
        const parts = [];
        if (groups > 0) parts.push(`${groups} GROUP${groups !== 1 ? 'S' : ''}`);
        if (assets > 0) parts.push(`${assets} ASSET${assets !== 1 ? 'S' : ''}`);
        countEl.textContent = parts.join(' + ') || '0';
    }

    // ================================================================
    //  GROUP DETAIL VIEW — Render assets, stubs, and edges
    // ================================================================

    _renderGroupView(data) {
        const nodes = data.nodes.map(n => ({...n}));
        const edges = data.edges.map(e => ({...e}));
        const externalEdges = (data.external_edges || []).map(e => ({...e}));

        const stubNodes = this._buildStubNodes(externalEdges);
        this._computeGroupLayout(nodes, edges);
        this._positionGroupStubNodes(stubNodes, nodes);

        const extEdgeMapped = externalEdges.map(ext =>
            ext.direction === 'inbound'
                ? {source: ext.external_asset, target: ext.target, _isExternal: true}
                : {source: ext.source, target: ext.external_asset, _isExternal: true},
        );

        // --- Internal edges ---
        const edgeGroups = this.g.append('g').attr('class', 'edges')
            .selectAll('g').data(edges).join('g').attr('class', 'edge-group');

        edgeGroups.append('path').attr('class', 'edge-glow-layer')
            .attr('fill', 'none').attr('stroke', 'url(#edge-gradient)')
            .attr('stroke-width', 4).attr('opacity', 0.2)
            .attr('filter', 'url(#edge-glow)');
        edgeGroups.append('path').attr('class', 'edge-main')
            .attr('fill', 'none').attr('stroke', 'url(#edge-gradient)')
            .attr('stroke-width', 2);
        this.edgeGroups = edgeGroups;

        // --- External edges (dashed) ---
        const extEdgeGroups = this.g.append('g').attr('class', 'external-edges')
            .selectAll('g').data(extEdgeMapped).join('g')
            .attr('class', 'edge-group edge-group-external');

        extEdgeGroups.append('path').attr('class', 'edge-main')
            .attr('fill', 'none').attr('stroke', '#6a6a80')
            .attr('stroke-width', 1.5).attr('stroke-dasharray', '8 4')
            .attr('opacity', 0.4).attr('marker-end', 'url(#arrow-external)');
        this.externalEdgeGroups = extEdgeGroups;

        // --- Asset nodes ---
        const NODE_HEIGHT = 44;
        const MIN_NODE_WIDTH = 130;
        const NODE_PADDING = 28;

        const nodeGroups = this.g.append('g').attr('class', 'nodes')
            .selectAll('g').data(nodes).join('g').attr('class', 'node')
            .call(this.drag());

        nodeGroups.append('text')
            .attr('text-anchor', 'middle').attr('dy', '0.35em')
            .text(d => d.name);

        nodeGroups.each(function(d) {
            const tw = d3.select(this).select('text').node().getComputedTextLength();
            d._nodeWidth = Math.max(MIN_NODE_WIDTH, tw + NODE_PADDING);
            d._nodeHeight = NODE_HEIGHT;
        });

        nodeGroups.insert('rect', 'text')
            .attr('width', d => d._nodeWidth).attr('height', NODE_HEIGHT)
            .attr('x', d => -d._nodeWidth / 2).attr('y', -NODE_HEIGHT / 2)
            .attr('rx', 4)
            .style('fill', d => `url(#gradient-${d.group in GROUP_COLORS ? d.group : 'default'})`)
            .style('stroke', d => (GROUP_COLORS[d.group] || GROUP_COLORS.default).stroke)
            .style('filter', d => {
                const c = GROUP_COLORS[d.group] || GROUP_COLORS.default;
                return `drop-shadow(0 0 8px ${c.stroke}66)`;
            });

        // Execution type icons
        nodeGroups.each(function(d) {
            const symbolId = EXECUTION_TYPE_ICONS[d.execution_type];
            if (!symbolId) return;
            const node = d3.select(this);
            const halfW = d._nodeWidth / 2;
            node.append('use').attr('class', 'exec-type-icon')
                .attr('href', `#${symbolId}`)
                .attr('width', 12).attr('height', 12)
                .attr('x', halfW - 15).attr('y', NODE_HEIGHT / 2 - 15)
                .style('opacity', 0.85);
        });

        // Check slivers
        const cyanShades = ['#68b5c2', '#5ca0ac', '#508e9a', '#457c88', '#78c2ce'];
        nodeGroups.each(function(d) {
            const checks = d.checks || [];
            if (checks.length === 0) return;
            const node = d3.select(this);
            const halfW = d._nodeWidth / 2;
            checks.forEach((check, i) => {
                const color = cyanShades[i % cyanShades.length];
                node.append('rect').attr('class', 'check-sliver')
                    .attr('width', 4).attr('height', NODE_HEIGHT)
                    .attr('x', halfW + 2 + i * 5).attr('y', -NODE_HEIGHT / 2)
                    .attr('rx', 1)
                    .style('fill', color)
                    .style('filter', `drop-shadow(0 0 4px ${color}cc)`)
                    .append('title').text(check.name);
            });
        });

        nodeGroups.attr('transform', d => `translate(${d.x},${d.y})`);
        this.nodeElements = nodeGroups;

        // --- Stub nodes ---
        const STUB_HEIGHT = 32;
        const stubGroups = this.g.append('g').attr('class', 'stub-nodes')
            .selectAll('g').data(stubNodes).join('g')
            .attr('class', 'node node-stub');

        stubGroups.append('text')
            .attr('text-anchor', 'middle').attr('dy', '0.35em')
            .style('font-size', '0.7rem').style('opacity', 0.5)
            .text(d => d.name);

        stubGroups.each(function(d) {
            const tw = d3.select(this).select('text').node().getComputedTextLength();
            d._nodeWidth = Math.max(80, tw + 24);
        });

        stubGroups.insert('rect', 'text')
            .attr('width', d => d._nodeWidth).attr('height', STUB_HEIGHT)
            .attr('x', d => -d._nodeWidth / 2).attr('y', -STUB_HEIGHT / 2)
            .attr('rx', 3)
            .style('fill', 'url(#gradient-stub)')
            .style('stroke', '#6a6a80').style('stroke-width', 1)
            .style('opacity', 0.5);

        stubGroups.attr('transform', d => `translate(${d.x},${d.y})`);
        this.stubNodeElements = stubGroups;

        // --- Update edge paths ---
        this._groupNodeMap = new Map([...nodes, ...stubNodes].map(n => [n.id, n]));
        const allNodeMap = this._groupNodeMap;
        const computePath = (src, tgt) => {
            const srcHW = (src._nodeWidth || 130) / 2;
            const tgtHW = (tgt._nodeWidth || 130) / 2;
            const srcChecks = src.checks ? src.checks.length : 0;
            const sliver = srcChecks > 0 ? srcChecks * 5 + 2 : 0;
            const sx = src.x + srcHW + (src._isStub ? 0 : sliver);
            const sy = src.y;
            const tx = tgt.x - tgtHW;
            const ty = tgt.y;
            const dx = tx - sx;
            const dy = ty - sy;
            const cv = Math.min(Math.abs(dx) * 0.3, 60);
            if (Math.abs(dy) < 30) {
                const mx = sx + dx * 0.5;
                const my = sy + dy * 0.5;
                return `M${sx},${sy} Q${mx},${my - Math.sign(dy || 1) * cv * 0.3} ${tx},${ty}`;
            }
            return `M${sx},${sy} C${sx + cv},${sy} ${tx - cv},${ty} ${tx},${ty}`;
        };

        edgeGroups.each(function(e) {
            const s = allNodeMap.get(typeof e.source === 'object' ? e.source.id : e.source);
            const t = allNodeMap.get(typeof e.target === 'object' ? e.target.id : e.target);
            if (s && t) d3.select(this).selectAll('path').attr('d', computePath(s, t));
        });
        extEdgeGroups.each(function(e) {
            const s = allNodeMap.get(typeof e.source === 'object' ? e.source.id : e.source);
            const t = allNodeMap.get(typeof e.target === 'object' ? e.target.id : e.target);
            if (s && t) d3.select(this).selectAll('path').attr('d', computePath(s, t));
        });

        // --- Count display ---
        const countEl = document.getElementById('overview-count');
        if (countEl) countEl.textContent = `${nodes.length} ASSET${nodes.length !== 1 ? 'S' : ''}`;

        // --- Group view interactions ---
        this._setupGroupViewInteractions(nodes, edges, externalEdges, stubNodes);

        // --- Fit to content ---
        this._fitGroupToContent([...nodes, ...stubNodes]);
    }

    _buildStubNodes(externalEdges) {
        const stubMap = new Map();
        externalEdges.forEach(ext => {
            const id = ext.external_asset;
            if (!stubMap.has(id)) {
                stubMap.set(id, {
                    id,
                    name: id.includes('/') ? id.split('/').pop() : id,
                    group: 'stub',
                    _isStub: true,
                    _stubDirection: ext.direction,
                    checks: [],
                });
            }
        });
        return Array.from(stubMap.values());
    }

    _computeGroupLayout(nodes, edges) {
        const deps = new Map();
        nodes.forEach(n => deps.set(n.id, []));
        edges.forEach(e => {
            const sid = typeof e.source === 'object' ? e.source.id : e.source;
            const tid = typeof e.target === 'object' ? e.target.id : e.target;
            if (deps.has(tid)) deps.get(tid).push(sid);
        });

        const levels = new Map();
        const computeLevel = (id, visited = new Set()) => {
            if (levels.has(id)) return levels.get(id);
            if (visited.has(id)) return 0;
            visited.add(id);
            const d = deps.get(id) || [];
            if (d.length === 0) { levels.set(id, 0); return 0; }
            const mx = Math.max(...d.map(x => computeLevel(x, visited)));
            levels.set(id, mx + 1);
            return mx + 1;
        };
        nodes.forEach(n => computeLevel(n.id));

        const lvlGroups = new Map();
        nodes.forEach(n => {
            const l = levels.get(n.id);
            if (!lvlGroups.has(l)) lvlGroups.set(l, []);
            lvlGroups.get(l).push(n);
        });

        const sorted = Array.from(lvlGroups.keys()).sort((a, b) => a - b);
        const maxLvl = sorted[sorted.length - 1] || 0;
        const hSp = 200, vSp = 80;
        const startX = -(maxLvl * hSp) / 2;

        sorted.forEach(level => {
            const atLevel = lvlGroups.get(level);
            const h = atLevel.length * vSp;
            const startY = -h / 2 + vSp / 2;
            atLevel.forEach((node, i) => {
                node.x = startX + level * hSp;
                node.y = startY + i * vSp;
                node.fx = node.x;
                node.fy = node.y;
            });
        });

        this._groupLayoutMinX = Infinity;
        this._groupLayoutMaxX = -Infinity;
        nodes.forEach(n => {
            const hw = (n._nodeWidth || 130) / 2;
            if (n.x - hw < this._groupLayoutMinX) this._groupLayoutMinX = n.x - hw;
            if (n.x + hw > this._groupLayoutMaxX) this._groupLayoutMaxX = n.x + hw;
        });
    }

    _positionGroupStubNodes(stubNodes, nodes) {
        const MARGIN = 120, vSp = 60;

        const inbound = stubNodes.filter(s => s._stubDirection === 'inbound');
        const outbound = stubNodes.filter(s => s._stubDirection === 'outbound');

        const lx = this._groupLayoutMinX - MARGIN;
        const inH = inbound.length * vSp;
        const inY0 = -inH / 2 + vSp / 2;
        inbound.forEach((s, i) => { s.x = lx; s.y = inY0 + i * vSp; s.fx = s.x; s.fy = s.y; });

        const rx = this._groupLayoutMaxX + MARGIN;
        const outH = outbound.length * vSp;
        const outY0 = -outH / 2 + vSp / 2;
        outbound.forEach((s, i) => { s.x = rx; s.y = outY0 + i * vSp; s.fx = s.x; s.fy = s.y; });
    }

    _fitGroupToContent(allNodes) {
        if (allNodes.length === 0) return;
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        allNodes.forEach(n => {
            const hw = (n._nodeWidth || 130) / 2;
            const hh = n._isStub ? 16 : 22;
            const sl = (n.checks && n.checks.length > 0) ? n.checks.length * 5 + 2 : 0;
            if (n.x - hw < minX) minX = n.x - hw;
            if (n.x + hw + sl > maxX) maxX = n.x + hw + sl;
            if (n.y - hh < minY) minY = n.y - hh;
            if (n.y + hh > maxY) maxY = n.y + hh;
        });
        const cw = maxX - minX, ch = maxY - minY;
        const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
        const hH = 64, pad = 60;
        const aW = this.width - pad * 2, aH = this.height - hH - pad;
        if (aW <= 0 || aH <= 0) return;
        const scale = Math.min(aW / cw, aH / ch, 1.2);
        const tx = this.width / 2 - cx * scale;
        const ty = hH + aH / 2 - cy * scale + pad / 2;
        this.svg.call(this.zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
    }

    _updateGroupEdgePaths() {
        if (!this._groupNodeMap) return;
        const nodeMap = this._groupNodeMap;

        const computePath = (src, tgt) => {
            const srcHW = (src._nodeWidth || 130) / 2;
            const tgtHW = (tgt._nodeWidth || 130) / 2;
            const srcChecks = src.checks ? src.checks.length : 0;
            const sliver = srcChecks > 0 ? srcChecks * 5 + 2 : 0;
            const sx = src.x + srcHW + (src._isStub ? 0 : sliver);
            const sy = src.y;
            const tx = tgt.x - tgtHW;
            const ty = tgt.y;
            const dx = tx - sx;
            const dy = ty - sy;
            const cv = Math.min(Math.abs(dx) * 0.3, 60);
            if (Math.abs(dy) < 30) {
                const mx = sx + dx * 0.5;
                const my = sy + dy * 0.5;
                return `M${sx},${sy} Q${mx},${my - Math.sign(dy || 1) * cv * 0.3} ${tx},${ty}`;
            }
            return `M${sx},${sy} C${sx + cv},${sy} ${tx - cv},${ty} ${tx},${ty}`;
        };

        if (this.edgeGroups) {
            this.edgeGroups.each(function(e) {
                const s = nodeMap.get(typeof e.source === 'object' ? e.source.id : e.source);
                const t = nodeMap.get(typeof e.target === 'object' ? e.target.id : e.target);
                if (s && t) d3.select(this).selectAll('path').attr('d', computePath(s, t));
            });
        }
        if (this.externalEdgeGroups) {
            this.externalEdgeGroups.each(function(e) {
                const s = nodeMap.get(typeof e.source === 'object' ? e.source.id : e.source);
                const t = nodeMap.get(typeof e.target === 'object' ? e.target.id : e.target);
                if (s && t) d3.select(this).selectAll('path').attr('d', computePath(s, t));
            });
        }
    }

    _setupGroupViewInteractions(nodes, edges, externalEdges, stubNodes) {
        const tooltip = document.getElementById('tooltip');
        const self = this;

        this.nodeElements
            .on('mouseenter', function(event, d) {
                if (self._isDragging) return;
                const checks = d.checks || [];
                const checkLine = checks.length > 0
                    ? `<div style="color: #68b5c2; font-size: 0.7rem; margin-top: 4px; font-family: 'Orbitron', sans-serif;">${checks.length} CHECK${checks.length !== 1 ? 'S' : ''}</div>`
                    : '';
                tooltip.innerHTML = `
                    <div class="font-display font-bold" style="color: #68b5c2;">${d.name}</div>
                    <div style="color: #8282a0; font-size: 0.7rem; letter-spacing: 0.1em; margin-top: 4px;">${d.group.toUpperCase()}</div>
                    ${d.return_type ? `<div style="color: #c45270; font-size: 0.75rem; margin-top: 6px; font-family: 'Space Mono', monospace;">${d.return_type}</div>` : ''}
                    ${checkLine}
                `;
                tooltip.style.opacity = '1';
                self._highlightGroupConnections(d, edges, externalEdges);
            })
            .on('mousemove', (event) => {
                tooltip.style.left = `${event.pageX + 10}px`;
                tooltip.style.top = `${event.pageY + 10}px`;
            })
            .on('mouseleave', () => {
                tooltip.style.opacity = '0';
                this._clearGroupHighlights();
            })
            .on('click', (event, d) => {
                if (event.defaultPrevented) return;
                if (d._dragged) {
                    d._dragged = false;
                    return;
                }
                event.stopPropagation();
                window.location.href = '/asset/' + encodeURIComponent(d.id);
            });

        if (this.stubNodeElements) {
            this.stubNodeElements
                .on('mouseenter', (event, d) => {
                    tooltip.innerHTML = `
                        <div class="font-display font-bold" style="color: #6a6a80;">${d.name}</div>
                        <div style="color: #5a5a72; font-size: 0.7rem; letter-spacing: 0.1em; margin-top: 4px;">EXTERNAL</div>
                    `;
                    tooltip.style.opacity = '1';
                })
                .on('mousemove', (event) => {
                    tooltip.style.left = `${event.pageX + 10}px`;
                    tooltip.style.top = `${event.pageY + 10}px`;
                })
                .on('mouseleave', () => { tooltip.style.opacity = '0'; });
        }
    }

    _highlightGroupConnections(node, edges, externalEdges) {
        const connected = new Set();
        edges.forEach(e => {
            const s = typeof e.source === 'object' ? e.source.id : e.source;
            const t = typeof e.target === 'object' ? e.target.id : e.target;
            if (s === node.id) connected.add(t);
            if (t === node.id) connected.add(s);
        });
        externalEdges.forEach(e => {
            if (e.source === node.id || e.target === node.id) connected.add(e.external_asset);
        });

        this.edgeGroups.each(function(e) {
            const s = typeof e.source === 'object' ? e.source.id : e.source;
            const t = typeof e.target === 'object' ? e.target.id : e.target;
            const hit = s === node.id || t === node.id;
            const g = d3.select(this);
            g.select('.edge-glow-layer')
                .attr('stroke', hit ? 'url(#edge-gradient-highlight)' : 'url(#edge-gradient)')
                .attr('stroke-width', hit ? 8 : 4)
                .attr('opacity', hit ? 0.4 : 0.2)
                .attr('filter', hit ? 'url(#edge-glow-intense)' : 'url(#edge-glow)');
            g.select('.edge-main')
                .attr('stroke', hit ? 'url(#edge-gradient-highlight)' : 'url(#edge-gradient)')
                .attr('stroke-width', hit ? 2.5 : 2);
        });

        if (this.externalEdgeGroups) {
            this.externalEdgeGroups.each(function(e) {
                const s = typeof e.source === 'object' ? e.source.id : e.source;
                const t = typeof e.target === 'object' ? e.target.id : e.target;
                const hit = s === node.id || t === node.id;
                d3.select(this).select('.edge-main')
                    .attr('opacity', hit ? 0.7 : 0.4)
                    .attr('stroke-width', hit ? 2 : 1.5);
            });
        }

        this.nodeElements.style('opacity', d =>
            d.id === node.id || connected.has(d.id) ? 1 : 0.3);
        if (this.stubNodeElements) {
            this.stubNodeElements.style('opacity', d =>
                connected.has(d.id) ? 0.7 : 0.2);
        }
    }

    _clearGroupHighlights() {
        this.edgeGroups.each(function() {
            const g = d3.select(this);
            g.select('.edge-glow-layer')
                .attr('stroke', 'url(#edge-gradient)').attr('stroke-width', 4)
                .attr('opacity', 0.2).attr('filter', 'url(#edge-glow)');
            g.select('.edge-main')
                .attr('stroke', 'url(#edge-gradient)').attr('stroke-width', 2);
        });
        if (this.externalEdgeGroups) {
            this.externalEdgeGroups.each(function() {
                d3.select(this).select('.edge-main')
                    .attr('opacity', 0.4).attr('stroke-width', 1.5);
            });
        }
        this.nodeElements.style('opacity', 1);
        if (this.stubNodeElements) this.stubNodeElements.style('opacity', 1);
    }

    // ================================================================
    //  ASSET-NODE MAPPING (for execution status tracking)
    // ================================================================

    _rebuildGroupAssetNodeMapping(groupData) {
        this.assetToNodeId.clear();
        this.groupAssetStatuses.clear();
        for (const node of groupData.nodes) {
            this.assetToNodeId.set(node.id, node.id);
        }
    }

    _rebuildOverviewAssetNodeMapping() {
        this.assetToNodeId.clear();
        this.groupAssetStatuses.clear();
        if (this._fullGraphNodes) {
            for (const asset of this._fullGraphNodes) {
                if (asset.group === 'default') {
                    this.assetToNodeId.set(asset.id, asset.id);
                } else {
                    this.assetToNodeId.set(asset.id, `group:${asset.group}`);
                }
            }
        }
    }

    // ================================================================
    //  ENTRANCE ANIMATIONS
    // ================================================================

    applyEntranceAnimations() {
        // Intentionally instant — no animation delay.
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('overview-graph-container');
    if (!container) return;

    new OverviewGraph('overview-graph-container');
});
