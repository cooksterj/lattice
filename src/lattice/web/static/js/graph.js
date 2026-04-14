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
    dbt: {start: '#e87d3e', end: '#7a3a14', stroke: '#f0954e'},        // dbt Orange
    jaffle_shop: {start: '#e87d3e', end: '#7a3a14', stroke: '#f0954e'}, // dbt Orange
};

// Execution type → symbol ID (defined in setupDefs)
const EXECUTION_TYPE_ICONS = {
    dbt:    'icon-dbt',
    python: 'icon-python',
    shell:  'icon-shell',
};

class LatticeGraph {
    constructor(container) {
        this.container = container;
        this.svg = null;
        this.simulation = null;
        this.nodes = [];
        this.edges = [];
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
        this.setupContextMenu();
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

        // === EXECUTION TYPE ICON SYMBOLS ===
        // dbt logo (Simple Icons)
        const dbtSymbol = defs.append('symbol')
            .attr('id', 'icon-dbt')
            .attr('viewBox', '0 0 24 24');
        dbtSymbol.append('path')
            .attr('fill', '#e87d3e')
            .attr('d', 'M17.9 9.38a8.15 8.15 0 0 0-3.04-3.12l1.77.84a10.29 10.29 0 0 1 3.74 3l3.23-5.93a2.85 2.85 0 0 0-.06-2.96 2.86 2.86 0 0 0-3.57-.86l-5.87 3.21a4.36 4.36 0 0 1-4.18 0L4.18.41a2.85 2.85 0 0 0-2.96.06A2.86 2.86 0 0 0 .35 3.97l3.2 5.94a4.36 4.36 0 0 1 0 4.18l-3.13 5.74a2.86 2.86 0 0 0 .09 3 2.86 2.86 0 0 0 3.54.84l6.06-3.3a10.29 10.29 0 0 1-3-3.75l-.84-1.77a8.15 8.15 0 0 0 3.12 3.04l10.58 5.78a2.86 2.86 0 0 0 3.54-.84 2.87 2.87 0 0 0 .08-3L17.9 9.38zm3.38-7.74a1.09 1.09 0 1 1 0 2.18 1.09 1.09 0 0 1 0-2.18zM2.74 3.82a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18zm0 18.54a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18zm10.36-11.45a2.17 2.17 0 0 0-2.18 2.17c0 .62.26 1.2.7 1.61a2.72 2.72 0 1 1 3.07-4.48 2.16 2.16 0 0 0-1.6-.7v.4zm8.18 11.45a1.09 1.09 0 1 1 0-2.18 1.09 1.09 0 0 1 0 2.18z');

        // Python logo (Simple Icons)
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
            .attr('fill', d => {
                return `url(#gradient-${d.group in GROUP_COLORS ? d.group : 'default'})`;
            })
            .attr('stroke', d => {
                const colors = GROUP_COLORS[d.group] || GROUP_COLORS.default;
                return colors.stroke;
            })
            .attr('filter', d => {
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

        // Execution type icons (bottom-right corner of node)
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

        // Node hover
        this.nodeElements
            .on('mouseenter', (event, d) => {
                tooltip.innerHTML = `
                    <div class="font-display font-bold" style="color: #68b5c2;">${d.name}</div>
                    <div style="color: #8282a0; font-size: 0.7rem; letter-spacing: 0.1em; margin-top: 4px;">${d.group.toUpperCase()}</div>
                    ${d.return_type ? `<div style="color: #c45270; font-size: 0.75rem; margin-top: 6px; font-family: 'Space Mono', monospace;">${d.return_type}</div>` : ''}
                    <div style="color: #5a5a72; font-size: 0.65rem; margin-top: 6px; letter-spacing: 0.05em;">CLICK: details</div>
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
                window.location.href = '/asset/' + encodeURIComponent(d.id);
            })
            .on('contextmenu', (event, d) => {
                event.preventDefault();
                event.stopPropagation();
                this.showContextMenu(event, d);
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

        this.nodeElements.classed('selected', d => d.id === node.id);

        // Show loading state
        content.innerHTML = '<div style="color: #68b5c2; font-family: Orbitron, sans-serif; letter-spacing: 0.2em; animation: textFlicker 1.5s ease-in-out infinite;">LOADING...</div>';
        sidebar.classList.remove('translate-x-full');

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

                <div class="detail-section">
                    <div class="detail-label">Execution Type</div>
                    <div class="detail-value" style="display: flex; align-items: center; gap: 8px; letter-spacing: 0.1em;">
                        <svg width="16" height="16"><use href="#${EXECUTION_TYPE_ICONS[data.execution_type] || 'icon-python'}"/></svg>
                        <span>${(data.execution_type || 'python').toUpperCase()}</span>
                    </div>
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

                ${data.metadata ? `
                <div class="detail-section">
                    <div class="detail-label">Metadata</div>
                    <div style="display: flex; flex-direction: column; gap: 6px;">
                        ${Object.entries(data.metadata).map(([k, v]) => `
                            <div style="display: flex; justify-content: space-between; font-size: 0.8rem;">
                                <span style="color: #8282a0; letter-spacing: 0.05em;">${k.toUpperCase()}</span>
                                <span style="color: #d0b454; font-family: 'Space Mono', monospace;">${Array.isArray(v) ? v.join(', ') : v}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
                ` : ''}

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

    setupContextMenu() {
        const menu = document.getElementById('context-menu');
        if (!menu) return;

        document.addEventListener('click', () => menu.classList.remove('visible'));
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') menu.classList.remove('visible');
        });

        document.getElementById('ctx-run-downstream')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const targetId = menu.dataset.targetId;
            if (targetId) {
                fetch('/api/execution/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({target: targetId, include_downstream: true}),
                }).then(() => { window.location.href = '/'; });
            }
            menu.classList.remove('visible');
        });

        document.getElementById('ctx-run-only')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const targetId = menu.dataset.targetId;
            if (targetId) {
                fetch('/api/execution/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({target: targetId, include_downstream: false}),
                }).then(() => { window.location.href = '/'; });
            }
            menu.classList.remove('visible');
        });

        document.getElementById('ctx-view-details')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const targetId = menu.dataset.targetId;
            if (targetId) window.location.href = '/asset/' + encodeURIComponent(targetId);
            menu.classList.remove('visible');
        });
    }

    showContextMenu(event, assetData) {
        const menu = document.getElementById('context-menu');
        if (!menu) return;

        const assetId = assetData.id;
        menu.dataset.targetId = assetId;

        const targetEl = document.getElementById('context-menu-target');
        const displayName = assetId.includes('/') ? assetId.split('/').pop() : assetId;
        targetEl.textContent = displayName.toUpperCase();

        const menuWidth = 260;
        const menuHeight = 300;
        let x = event.clientX;
        let y = event.clientY;
        if (x + menuWidth > window.innerWidth) x = window.innerWidth - menuWidth - 8;
        if (y + menuHeight > window.innerHeight) y = window.innerHeight - menuHeight - 8;
        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;
        menu.classList.add('visible');

        const preview = document.getElementById('context-menu-preview');
        preview.innerHTML = '<div class="context-menu-preview-loading">LOADING PLAN...</div>';

        fetch(`/api/plan?target=${encodeURIComponent(assetId)}&include_downstream=true`)
            .then(r => r.json())
            .then(data => {
                const steps = data.steps || [];
                if (steps.length === 0) {
                    preview.innerHTML = '<div class="context-menu-preview-title">NO ASSETS</div>';
                    return;
                }
                preview.innerHTML = `
                    <div class="context-menu-preview-title">EXECUTION PLAN (${steps.length})</div>
                    <div class="context-menu-preview-list">
                        ${steps.map(s =>
                            `<div class="context-menu-preview-asset${s.id === assetId ? ' is-target' : ''}">${s.id}</div>`
                        ).join('')}
                    </div>
                `;
            })
            .catch(() => {
                preview.innerHTML = '<div class="context-menu-preview-title">FAILED TO LOAD</div>';
            });
    }

    hideLoading() {
        document.getElementById('loading').style.display = 'none';
    }

}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    new LatticeGraph('graph-container');
});
