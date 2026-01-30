/**
 * Lattice Graph Visualization
 * D3.js force-directed graph with interactive features
 */

const GROUP_COLORS = {
    default: { start: '#6366f1', end: '#4f46e5' },
    analytics: { start: '#10b981', end: '#059669' },
    data: { start: '#f59e0b', end: '#d97706' },
    ml: { start: '#ec4899', end: '#db2777' },
    etl: { start: '#8b5cf6', end: '#7c3aed' },
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

            this.nodes = data.nodes.map(n => ({ ...n }));
            this.edges = data.edges.map(e => ({ ...e }));

            // Update asset count
            document.getElementById('asset-count').textContent =
                `${this.nodes.length} asset${this.nodes.length !== 1 ? 's' : ''}`;

        } catch (error) {
            console.error('Failed to load graph data:', error);
            document.getElementById('asset-count').textContent = 'Error loading data';
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

        // Node rectangles
        this.nodeElements.append('rect')
            .attr('width', 120)
            .attr('height', 40)
            .attr('x', -60)
            .attr('y', -20)
            .attr('rx', 8)
            .attr('class', d => `group-${d.group}`)
            .style('fill', d => {
                const colors = GROUP_COLORS[d.group] || GROUP_COLORS.default;
                return `url(#gradient-${d.group in GROUP_COLORS ? d.group : 'default'})`;
            });

        // Node labels
        this.nodeElements.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '0.35em')
            .text(d => d.name.length > 14 ? d.name.slice(0, 12) + '...' : d.name);

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
                    <div class="font-semibold">${d.name}</div>
                    <div class="text-gray-400 text-xs">${d.group}</div>
                    ${d.return_type ? `<div class="text-indigo-400 text-xs font-mono mt-1">${d.return_type}</div>` : ''}
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
            document.documentElement.classList.toggle('dark');
            document.documentElement.classList.toggle('light');
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
        content.innerHTML = '<div class="loading-pulse text-gray-400">Loading...</div>';
        sidebar.classList.remove('translate-x-full');

        try {
            const response = await fetch(`/api/assets/${encodeURIComponent(node.id)}`);
            const data = await response.json();

            content.innerHTML = `
                <div class="detail-section">
                    <div class="detail-label">Name</div>
                    <div class="detail-value font-semibold text-lg">${data.name}</div>
                </div>

                <div class="detail-section">
                    <div class="detail-label">Group</div>
                    <div class="detail-value">${data.group}</div>
                </div>

                ${data.return_type ? `
                <div class="detail-section">
                    <div class="detail-label">Return Type</div>
                    <div class="detail-value font-mono text-indigo-400">${data.return_type}</div>
                </div>
                ` : ''}

                ${data.description ? `
                <div class="detail-section">
                    <div class="detail-label">Description</div>
                    <div class="detail-value text-gray-300">${data.description}</div>
                </div>
                ` : ''}

                <div class="detail-section">
                    <div class="detail-label">Dependencies (${data.dependencies.length})</div>
                    <div class="dep-list">
                        ${data.dependencies.length > 0
                            ? data.dependencies.map(d => `<span class="dep-badge" data-asset="${d}">${d}</span>`).join('')
                            : '<span class="text-gray-500 text-sm">None</span>'}
                    </div>
                </div>

                <div class="detail-section">
                    <div class="detail-label">Dependents (${data.dependents.length})</div>
                    <div class="dep-list">
                        ${data.dependents.length > 0
                            ? data.dependents.map(d => `<span class="dep-badge" data-asset="${d}">${d}</span>`).join('')
                            : '<span class="text-gray-500 text-sm">None</span>'}
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
            content.innerHTML = `<div class="text-red-400">Failed to load asset details</div>`;
        }
    }

    hideLoading() {
        document.getElementById('loading').style.display = 'none';
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    new LatticeGraph('graph-container');
});
