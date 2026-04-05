/**
 * Lattice Group Graph Visualization
 * Stripped-down variant of graph.js for rendering a dependency graph
 * scoped to a single asset group, with external dependency stubs.
 */

// Reuse the same palette and icon constants as graph.js
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
    dbt:    'icon-dbt',
    python: 'icon-python',
    shell:  'icon-shell',
};

class GroupGraph {
    constructor(containerId, groupName) {
        this.container = containerId;
        this.groupName = groupName;
        this.svg = null;
        this.simulation = null;
        this.nodes = [];
        this.edges = [];
        this.externalEdges = [];
        this.stubNodes = [];
        this.width = 0;
        this.height = 0;

        this.init();
    }

    async init() {
        this.setupSVG();
        this.setupZoom();
        this.setupDefs();
        await this.loadData();
        this.render();
        this.setupEventListeners();
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

        // === EDGE GRADIENTS ===
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

        // === GLOW FILTERS ===
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
        const arrow = defs.append('marker')
            .attr('id', 'arrow')
            .attr('viewBox', '0 -6 14 12')
            .attr('refX', 12)
            .attr('refY', 0)
            .attr('markerWidth', 10)
            .attr('markerHeight', 10)
            .attr('orient', 'auto');
        arrow.append('path')
            .attr('d', 'M0,-5 L4,0 L0,5 L12,0 Z')
            .attr('fill', '#68b5c2')
            .attr('filter', 'drop-shadow(0 0 2px rgba(104,181,194,0.4))');

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

        // === EXTERNAL EDGE ARROW (muted) ===
        const arrowExternal = defs.append('marker')
            .attr('id', 'arrow-external')
            .attr('viewBox', '0 -6 14 12')
            .attr('refX', 12)
            .attr('refY', 0)
            .attr('markerWidth', 8)
            .attr('markerHeight', 8)
            .attr('orient', 'auto');
        arrowExternal.append('path')
            .attr('d', 'M0,-5 L4,0 L0,5 L12,0 Z')
            .attr('fill', '#6a6a80')
            .attr('opacity', 0.5);

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

        // Stub node gradient (muted gray)
        const stubGradient = defs.append('linearGradient')
            .attr('id', 'gradient-stub')
            .attr('x1', '0%')
            .attr('y1', '0%')
            .attr('x2', '100%')
            .attr('y2', '100%');
        stubGradient.append('stop')
            .attr('offset', '0%')
            .attr('stop-color', '#5a5a6e');
        stubGradient.append('stop')
            .attr('offset', '100%')
            .attr('stop-color', '#2e2e3e');

        // === EXECUTION TYPE ICON SYMBOLS ===
        // dbt logo
        const dbtSymbol = defs.append('symbol')
            .attr('id', 'icon-dbt')
            .attr('viewBox', '0 0 24 24');
        dbtSymbol.append('path')
            .attr('fill', '#e87d3e')
            .attr('d', 'M17.9 9.38a8.15 8.15 0 0 0-3.04-3.12l1.77.84a10.29 10.29 0 0 1 3.74 3l3.23-5.93a2.85 2.85 0 0 0-.06-2.96 2.86 2.86 0 0 0-3.57-.86l-5.87 3.21a4.36 4.36 0 0 1-4.18 0L4.18.41a2.85 2.85 0 0 0-2.96.06A2.86 2.86 0 0 0 .35 3.97l3.2 5.94a4.36 4.36 0 0 1 0 4.18l-3.13 5.74a2.86 2.86 0 0 0 .09 3 2.86 2.86 0 0 0 3.54.84l6.06-3.3a10.29 10.29 0 0 1-3-3.75l-.84-1.77a8.15 8.15 0 0 0 3.12 3.04l10.58 5.78a2.86 2.86 0 0 0 3.54-.84 2.87 2.87 0 0 0 .08-3L17.9 9.38zm3.38-7.74a1.09 1.09 0 1 1 0 2.18 1.09 1.09 0 0 1 0-2.18zM2.74 3.82a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18zm0 18.54a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18zm10.36-11.45a2.17 2.17 0 0 0-2.18 2.17c0 .62.26 1.2.7 1.61a2.72 2.72 0 1 1 3.07-4.48 2.16 2.16 0 0 0-1.6-.7v.4zm8.18 11.45a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18z');

        // Python logo
        const pySymbol = defs.append('symbol')
            .attr('id', 'icon-python')
            .attr('viewBox', '0 0 24 24');
        pySymbol.append('path')
            .attr('fill', '#68b5c2')
            .attr('d', 'M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.21.02H8.77l-.69.05-.59.14-.5.22-.41.27-.33.32-.27.35-.2.36-.15.37-.1.35-.07.32-.04.27-.02.21v3.06H3.17l-.21-.03-.28-.07-.32-.12-.35-.18-.36-.26-.36-.36-.35-.46-.32-.59-.28-.73-.21-.88-.14-1.05-.05-1.23.06-1.22.16-1.04.24-.87.32-.71.36-.57.4-.44.42-.33.42-.24.4-.16.36-.1.32-.05.24-.01h.16l.06.01h8.16v-.83H6.18l-.01-2.75-.02-.37.05-.34.11-.31.17-.28.25-.26.31-.23.38-.2.44-.18.51-.15.58-.12.64-.1.71-.06.77-.04.84-.02 1.27.05zm-6.3 1.98l-.23.33-.08.41.08.41.23.34.33.22.41.09.41-.09.33-.22.23-.34.08-.41-.08-.41-.23-.33-.33-.22-.41-.09-.41.09zm13.09 3.95l.28.06.32.12.35.18.36.27.36.35.35.47.32.59.28.73.21.88.14 1.04.05 1.23-.06 1.23-.16 1.04-.24.86-.32.71-.36.57-.4.45-.42.33-.42.24-.4.16-.36.09-.32.05-.24.02-.16-.01h-8.22v.82h5.84l.01 2.76.02.36-.05.34-.11.31-.17.29-.25.25-.31.24-.38.2-.44.17-.51.15-.58.13-.64.09-.71.07-.77.04-.84.01-1.27-.04-1.07-.14-.9-.2-.73-.25-.59-.3-.45-.33-.34-.34-.25-.34-.16-.33-.1-.3-.04-.25-.02-.2.01-.13v-5.34l.05-.64.13-.54.21-.46.26-.38.3-.32.33-.24.35-.2.35-.14.33-.1.3-.06.26-.04.21-.02.13-.01h5.84l.69-.05.59-.14.5-.21.41-.28.33-.32.27-.35.2-.36.15-.36.1-.35.07-.32.04-.28.02-.21V6.07h2.09l.14.01zm-6.47 14.25l-.23.33-.08.41.08.41.23.33.33.23.41.08.41-.08.33-.23.23-.33.08-.41-.08-.41-.23-.33-.33-.23-.41-.08-.41.08z');

        // Shell / terminal icon
        const shellSymbol = defs.append('symbol')
            .attr('id', 'icon-shell')
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
    }

    async loadData() {
        try {
            const response = await fetch(`/api/groups/${encodeURIComponent(this.groupName)}/graph`);
            const data = await response.json();

            this.nodes = data.nodes.map(n => ({...n}));
            this.edges = data.edges.map(e => ({...e}));
            this.externalEdges = (data.external_edges || []).map(e => ({...e}));

            // Build stub nodes from external edges
            this.buildStubNodes();

            // Update asset count (intra-group nodes only)
            const countEl = document.getElementById('asset-count');
            if (countEl) {
                countEl.textContent = String(this.nodes.length).padStart(3, '0');
            }

        } catch (error) {
            console.error('Failed to load group graph data:', error);
            const countEl = document.getElementById('asset-count');
            if (countEl) {
                countEl.textContent = 'ERR';
            }
        }
    }

    buildStubNodes() {
        const stubMap = new Map();

        this.externalEdges.forEach(ext => {
            const stubId = ext.external_asset;
            if (!stubMap.has(stubId)) {
                stubMap.set(stubId, {
                    id: stubId,
                    name: stubId.includes('/') ? stubId.split('/').pop() : stubId,
                    group: 'stub',
                    _isStub: true,
                    _stubDirection: ext.direction, // inbound or outbound
                    checks: [],
                });
            }
        });

        this.stubNodes = Array.from(stubMap.values());
    }

    render() {
        // Combine real nodes and stub nodes for layout
        const allNodes = [...this.nodes, ...this.stubNodes];

        // Build internal edges (source/target reference real node IDs)
        const internalEdges = this.edges.map(e => ({...e}));

        // Build external edges mapped to stub nodes
        const externalEdgeMapped = this.externalEdges.map(ext => {
            if (ext.direction === 'inbound') {
                // External asset -> internal target (upstream dependency)
                return {source: ext.external_asset, target: ext.target, _isExternal: true};
            } else {
                // Internal source -> external asset (downstream dependent)
                return {source: ext.source, target: ext.external_asset, _isExternal: true};
            }
        });

        const allEdges = [...internalEdges, ...externalEdgeMapped];

        // Store combined data for layout and tick
        this._allNodes = allNodes;
        this._allEdges = allEdges;

        // === RENDER INTERNAL EDGES ===
        const internalEdgeGroups = this.g.append('g')
            .attr('class', 'edges')
            .selectAll('g')
            .data(internalEdges)
            .join('g')
            .attr('class', 'edge-group');

        // Glow layer
        internalEdgeGroups.append('path')
            .attr('class', 'edge-glow-layer')
            .attr('fill', 'none')
            .attr('stroke', 'url(#edge-gradient)')
            .attr('stroke-width', 4)
            .attr('opacity', 0.2)
            .attr('filter', 'url(#edge-glow)');

        // Main edge
        internalEdgeGroups.append('path')
            .attr('class', 'edge-main')
            .attr('fill', 'none')
            .attr('stroke', 'url(#edge-gradient)')
            .attr('stroke-width', 2);

        this.edgeGroups = internalEdgeGroups;

        // === RENDER EXTERNAL EDGES (dashed) ===
        const externalEdgeGroups = this.g.append('g')
            .attr('class', 'external-edges')
            .selectAll('g')
            .data(externalEdgeMapped)
            .join('g')
            .attr('class', 'edge-group edge-group-external');

        externalEdgeGroups.append('path')
            .attr('class', 'edge-main')
            .attr('fill', 'none')
            .attr('stroke', '#6a6a80')
            .attr('stroke-width', 1.5)
            .attr('stroke-dasharray', '8 4')
            .attr('opacity', 0.4)
            .attr('marker-end', 'url(#arrow-external)');

        this.externalEdgeGroups = externalEdgeGroups;

        // === RENDER INTRA-GROUP NODES ===
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
        const NODE_PADDING = 28;
        this.nodeElements.each(function(d) {
            const textEl = d3.select(this).select('text').node();
            const textWidth = textEl.getComputedTextLength();
            d._nodeWidth = Math.max(MIN_NODE_WIDTH, textWidth + NODE_PADDING);
        });

        // Node rectangles with gradient and glow
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

        // Check slivers
        this.nodeElements.each(function(d) {
            const node = d3.select(this);
            const checks = d.checks || [];
            if (checks.length === 0) return;

            const cyanShades = [
                '#68b5c2', '#5ca0ac', '#508e9a', '#457c88', '#78c2ce',
            ];

            const sliverWidth = 4;
            const sliverGap = 1;
            const sliverHeight = 44;
            const halfWidth = d._nodeWidth / 2;
            const startX = halfWidth + 2;

            checks.forEach((check, i) => {
                const color = cyanShades[i % cyanShades.length];
                node.append('rect')
                    .attr('class', 'check-sliver')
                    .attr('width', sliverWidth)
                    .attr('height', sliverHeight)
                    .attr('x', startX + i * (sliverWidth + sliverGap))
                    .attr('y', -22)
                    .attr('rx', 1)
                    .style('fill', color)
                    .style('filter', `drop-shadow(0 0 4px ${color}cc)`)
                    .append('title')
                    .text(check.name);
            });
        });

        // Execution type icons
        this.nodeElements.each(function(d) {
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
                .attr('y', 22 - iconSize - padding)
                .style('opacity', 0.85);
        });

        // === RENDER STUB NODES ===
        const MIN_STUB_WIDTH = 80;
        const STUB_HEIGHT = 32;
        const STUB_PADDING = 24;

        this.stubNodeElements = this.g.append('g')
            .attr('class', 'stub-nodes')
            .selectAll('g')
            .data(this.stubNodes)
            .join('g')
            .attr('class', 'node node-stub');

        // Stub labels (render first to measure text width)
        this.stubNodeElements.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '0.35em')
            .style('font-size', '0.7rem')
            .style('opacity', 0.5)
            .text(d => d.name);

        // Measure each stub label and size the box to fit
        this.stubNodeElements.each(function(d) {
            const textEl = d3.select(this).select('text').node();
            const textWidth = textEl.getComputedTextLength();
            d._nodeWidth = Math.max(MIN_STUB_WIDTH, textWidth + STUB_PADDING);
        });

        // Stub rectangles sized to fit text
        this.stubNodeElements.insert('rect', 'text')
            .attr('width', d => d._nodeWidth)
            .attr('height', STUB_HEIGHT)
            .attr('x', d => -d._nodeWidth / 2)
            .attr('y', -STUB_HEIGHT / 2)
            .attr('rx', 3)
            .style('fill', 'url(#gradient-stub)')
            .style('stroke', '#6a6a80')
            .style('stroke-width', 1)
            .style('opacity', 0.5);

        // === LAYOUT ===
        this.computeHierarchicalLayout();

        // Position stub nodes at edges
        this.positionStubNodes();

        // Setup simulation with fixed positions
        this.simulation = d3.forceSimulation(allNodes)
            .force('link', d3.forceLink(allEdges)
                .id(d => d.id)
                .distance(150))
            .on('tick', () => this.tick())
            .on('end', () => this.lockAllNodes());

        this.lockAllNodes();
        this.simulation.stop();
        this.tick();
        this.fitToContent();
        this.applyEntranceAnimations();
    }

    computeHierarchicalLayout() {
        // Only layout real (non-stub) nodes hierarchically
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

        const horizontalSpacing = 200;
        const verticalSpacing = 80;
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

        // Store layout bounds for stub positioning
        this._layoutMinX = Infinity;
        this._layoutMaxX = -Infinity;

        this.nodes.forEach(n => {
            const halfW = (n._nodeWidth || 130) / 2;
            if (n.x - halfW < this._layoutMinX) this._layoutMinX = n.x - halfW;
            if (n.x + halfW > this._layoutMaxX) this._layoutMaxX = n.x + halfW;
        });
    }

    positionStubNodes() {
        // Position stub nodes at the left (inbound) or right (outbound) edges
        const STUB_MARGIN = 120;
        const verticalSpacing = 60;

        const inboundStubs = this.stubNodes.filter(s => s._stubDirection === 'inbound');
        const outboundStubs = this.stubNodes.filter(s => s._stubDirection === 'outbound');

        // Inbound stubs on the left
        const leftX = this._layoutMinX - STUB_MARGIN;
        const inboundHeight = inboundStubs.length * verticalSpacing;
        const inboundStartY = -inboundHeight / 2 + verticalSpacing / 2;

        inboundStubs.forEach((stub, i) => {
            stub.x = leftX;
            stub.y = inboundStartY + i * verticalSpacing;
            stub.fx = stub.x;
            stub.fy = stub.y;
        });

        // Outbound stubs on the right
        const rightX = this._layoutMaxX + STUB_MARGIN;
        const outboundHeight = outboundStubs.length * verticalSpacing;
        const outboundStartY = -outboundHeight / 2 + verticalSpacing / 2;

        outboundStubs.forEach((stub, i) => {
            stub.x = rightX;
            stub.y = outboundStartY + i * verticalSpacing;
            stub.fx = stub.x;
            stub.fy = stub.y;
        });
    }

    fitToContent() {
        if (this._allNodes.length === 0) return;

        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        this._allNodes.forEach(n => {
            const halfW = (n._nodeWidth || 130) / 2;
            const halfH = n._isStub ? 16 : 22;
            const sliverOffset = (n.checks && n.checks.length > 0) ? (n.checks.length * 5) + 2 : 0;
            if (n.x - halfW < minX) minX = n.x - halfW;
            if (n.x + halfW + sliverOffset > maxX) maxX = n.x + halfW + sliverOffset;
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
        const scale = Math.min(scaleX, scaleY, 1.2);

        const tx = this.width / 2 - centerX * scale;
        const ty = headerHeight + availableHeight / 2 - centerY * scale + padding / 2;

        const transform = d3.zoomIdentity.translate(tx, ty).scale(scale);
        this.svg.call(this.zoom.transform, transform);
    }

    tick() {
        const generatePath = (d) => {
            const sourceHalfWidth = (d.source._nodeWidth || 130) / 2;
            const targetHalfWidth = (d.target._nodeWidth || 130) / 2;

            const sourceChecks = d.source.checks ? d.source.checks.length : 0;
            const sliverOffset = sourceChecks > 0 ? (sourceChecks * 5) + 2 : 0;

            const sourceX = d.source.x + sourceHalfWidth + sliverOffset;
            const targetX = d.target.x - targetHalfWidth;
            const sourceY = d.source.y;
            const targetY = d.target.y;

            const dx = targetX - sourceX;
            const dy = targetY - sourceY;

            const curvature = Math.min(Math.abs(dx) * 0.3, 60);

            const midX = sourceX + dx * 0.5;
            const midY = sourceY + dy * 0.5;

            if (Math.abs(dy) < 30) {
                const controlY = midY - Math.sign(dy || 1) * curvature * 0.3;
                return `M${sourceX},${sourceY} Q${midX},${controlY} ${targetX},${targetY}`;
            } else {
                const c1x = sourceX + curvature;
                const c1y = sourceY;
                const c2x = targetX - curvature;
                const c2y = targetY;
                return `M${sourceX},${sourceY} C${c1x},${c1y} ${c2x},${c2y} ${targetX},${targetY}`;
            }
        };

        // For stub nodes the half-width calculation uses the smaller rect
        const generateExternalPath = (d) => {
            const sourceHalfWidth = (d.source._nodeWidth || 100) / 2;
            const targetHalfWidth = (d.target._nodeWidth || 100) / 2;

            const sourceChecks = d.source.checks ? d.source.checks.length : 0;
            const sliverOffset = sourceChecks > 0 ? (sourceChecks * 5) + 2 : 0;

            const sourceX = d.source.x + sourceHalfWidth + (d.source._isStub ? 0 : sliverOffset);
            const targetX = d.target.x - targetHalfWidth;
            const sourceY = d.source.y;
            const targetY = d.target.y;

            const dx = targetX - sourceX;
            const dy = targetY - sourceY;

            const curvature = Math.min(Math.abs(dx) * 0.3, 60);

            if (Math.abs(dy) < 30) {
                const midX = sourceX + dx * 0.5;
                const midY = sourceY + dy * 0.5;
                const controlY = midY - Math.sign(dy || 1) * curvature * 0.3;
                return `M${sourceX},${sourceY} Q${midX},${controlY} ${targetX},${targetY}`;
            } else {
                const c1x = sourceX + curvature;
                const c1y = sourceY;
                const c2x = targetX - curvature;
                const c2y = targetY;
                return `M${sourceX},${sourceY} C${c1x},${c1y} ${c2x},${c2y} ${targetX},${targetY}`;
            }
        };

        // Update internal edge paths
        this.edgeGroups.each(function(d) {
            const path = generatePath(d);
            d3.select(this).selectAll('path').attr('d', path);
        });

        // Update external edge paths
        this.externalEdgeGroups.each(function(d) {
            const path = generateExternalPath(d);
            d3.select(this).selectAll('path').attr('d', path);
        });

        // Update node positions
        this.nodeElements.attr('transform', d => `translate(${d.x},${d.y})`);
        this.stubNodeElements.attr('transform', d => `translate(${d.x},${d.y})`);
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
            });
    }

    lockAllNodes() {
        this._allNodes.forEach(d => {
            d.fx = d.x;
            d.fy = d.y;
        });
    }

    setupEventListeners() {
        const tooltip = document.getElementById('tooltip');

        // Node hover (intra-group nodes only)
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
                if (event.defaultPrevented) return;
                event.stopPropagation();
                window.location.href = '/asset/' + encodeURIComponent(d.id);
            });

        // Stub nodes: show tooltip but are non-clickable (no navigation)
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
            .on('mouseleave', () => {
                tooltip.style.opacity = '0';
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

        // Check internal edges
        this.edges.forEach(e => {
            const srcId = typeof e.source === 'object' ? e.source.id : e.source;
            const tgtId = typeof e.target === 'object' ? e.target.id : e.target;
            if (srcId === node.id) connectedIds.add(tgtId);
            if (tgtId === node.id) connectedIds.add(srcId);
        });

        // Check external edges
        this.externalEdges.forEach(e => {
            if (e.source === node.id || (typeof e.source === 'object' && e.source.id === node.id)) {
                connectedIds.add(e.external_asset);
            }
            if (e.target === node.id || (typeof e.target === 'object' && e.target.id === node.id)) {
                connectedIds.add(e.external_asset);
            }
        });

        // Highlight internal edge groups
        this.edgeGroups.each(function(e) {
            const srcId = typeof e.source === 'object' ? e.source.id : e.source;
            const tgtId = typeof e.target === 'object' ? e.target.id : e.target;
            const isConnected = srcId === node.id || tgtId === node.id;
            const group = d3.select(this);

            group.classed('highlighted', isConnected);

            group.select('.edge-glow-layer')
                .attr('stroke', isConnected ? 'url(#edge-gradient-highlight)' : 'url(#edge-gradient)')
                .attr('stroke-width', isConnected ? 8 : 4)
                .attr('opacity', isConnected ? 0.4 : 0.2)
                .attr('filter', isConnected ? 'url(#edge-glow-intense)' : 'url(#edge-glow)');

            group.select('.edge-main')
                .attr('stroke', isConnected ? 'url(#edge-gradient-highlight)' : 'url(#edge-gradient)')
                .attr('stroke-width', isConnected ? 2.5 : 2);
        });

        // Highlight external edge groups
        this.externalEdgeGroups.each(function(e) {
            const srcId = typeof e.source === 'object' ? e.source.id : e.source;
            const tgtId = typeof e.target === 'object' ? e.target.id : e.target;
            const isConnected = srcId === node.id || tgtId === node.id;
            const group = d3.select(this);

            group.select('.edge-main')
                .attr('opacity', isConnected ? 0.7 : 0.4)
                .attr('stroke-width', isConnected ? 2 : 1.5);
        });

        // Dim unconnected intra-group nodes
        this.nodeElements
            .style('opacity', d =>
                d.id === node.id || connectedIds.has(d.id) ? 1 : 0.3);

        // Dim unconnected stub nodes
        this.stubNodeElements
            .style('opacity', d => connectedIds.has(d.id) ? 0.7 : 0.2);
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

        this.externalEdgeGroups.each(function() {
            d3.select(this).select('.edge-main')
                .attr('opacity', 0.4)
                .attr('stroke-width', 1.5);
        });

        this.nodeElements.style('opacity', 1);
        this.stubNodeElements.style('opacity', 1);
    }

    hideLoading() {
        const loadingEl = document.getElementById('loading');
        if (loadingEl) {
            loadingEl.style.display = 'none';
        }
    }

    applyEntranceAnimations() {
        // Intentionally instant — no animation delay.
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('group-graph-container');
    if (!container) return;

    const groupName = container.getAttribute('data-group-name');
    if (!groupName) {
        console.error('group_graph.js: missing data-group-name attribute on #group-graph-container');
        return;
    }

    new GroupGraph('group-graph-container', groupName);
});
