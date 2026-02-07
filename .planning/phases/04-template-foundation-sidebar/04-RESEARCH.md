# Phase 4: Template Foundation & Sidebar - Research

**Researched:** 2026-02-07
**Domain:** Jinja2 template inheritance, CSS icon rail sidebar, server-side navigation
**Confidence:** HIGH

## Summary

Phase 4 introduces a persistent icon rail sidebar on every page and refactors all templates to use Jinja2 template inheritance. The research focused on three domains: (1) how to introduce a Jinja2 base template into the existing standalone templates, (2) how to build a CSS-only icon rail sidebar at ~48-56px width with active-page highlighting, and (3) how to ensure browser back/forward works with standard server-side navigation.

The existing codebase has 4 standalone HTML templates (index.html, asset_detail.html, asset_live.html, history.html), none of which use `{% extends %}` or `{% block %}`. Each duplicates the full `<head>`, header, theme toggle logic, and corner decorations. The phase must extract shared structure into a base template, add the sidebar, and update all child templates -- all without breaking existing functionality.

**Primary recommendation:** Create a `base.html` Jinja2 template with `{% block %}` zones for title, head_extra, page_class, and content. Add the sidebar as fixed markup in base.html. Pass a `current_page` variable from each FastAPI route handler so the sidebar can highlight the active icon via a simple Jinja2 conditional.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Jinja2 | 3.1.0+ (already installed) | Template inheritance, blocks, conditionals | Already the project's template engine |
| Tailwind CSS (CDN) | latest (already loaded) | Utility classes for layout | Already used via CDN script tag |
| Custom CSS (styles.css) | N/A | Design system variables, component styles | Already the main stylesheet |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None needed | - | - | No new dependencies required |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Jinja2 inheritance | Jinja2 `{% include %}` | Include works for partials but doesn't give block override capability; inheritance is better for full page layouts |
| CSS sidebar | JS-driven sidebar | Unnecessary complexity; CSS-only is sufficient for a fixed icon rail |
| Inline SVG icons | Icon library (Font Awesome, Lucide) | Adds a dependency; inline SVG keeps zero-dependency policy and matches existing pattern |

**Installation:**
```bash
# No new packages needed -- everything is already in the stack
```

## Architecture Patterns

### Recommended Template Structure

```
src/lattice/web/templates/
├── base.html              # NEW: base template with sidebar + shared structure
├── index.html             # MODIFY: extends base.html
├── history.html           # MODIFY: extends base.html
├── asset_detail.html      # MODIFY: extends base.html
└── asset_live.html        # MODIFY: extends base.html
```

### Pattern 1: Jinja2 Template Inheritance

**What:** A base template defines the overall page structure with named `{% block %}` zones. Child templates `{% extends "base.html" %}` and override only the blocks they need.

**When to use:** When multiple pages share header, sidebar, footer, CSS/JS includes.

**Example:**

```html
{# base.html #}
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LATTICE // {% block title %}{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    {# ... shared font links, stylesheet ... #}
    <link rel="stylesheet" href="/static/css/styles.css?v=10">
    {% block head_extra %}{% endblock %}
</head>
<body class="font-mono {% block body_class %}{% endblock %}">
    {# Sidebar #}
    <nav class="sidebar-rail">
        <a href="/" class="sidebar-icon {% if current_page == 'graph' %}active{% endif %}" title="Graph">
            {# SVG icon #}
        </a>
        <a href="/runs" class="sidebar-icon {% if current_page == 'runs' %}active{% endif %}" title="Active Runs">
            {# SVG icon #}
        </a>
        <a href="/history" class="sidebar-icon {% if current_page == 'history' %}active{% endif %}" title="Run History">
            {# SVG icon #}
        </a>
    </nav>

    {# Main content area shifted right by sidebar width #}
    <main class="main-content">
        {% block content %}{% endblock %}
    </main>

    {# Shared: corner decorations, theme script #}
    <div class="corner-decor top-left"></div>
    ...
    {% block scripts %}{% endblock %}
</body>
</html>
```

```html
{# index.html #}
{% extends "base.html" %}

{% block title %}Asset Graph{% endblock %}

{% block content %}
    {# Graph-specific content here #}
{% endblock %}

{% block scripts %}
    <script src="/static/js/graph.js?v=17"></script>
{% endblock %}
```

**Key insight:** The `current_page` variable is passed from the FastAPI route handler as a template context variable. This is the simplest approach for server-rendered pages -- no JavaScript needed for active state.

### Pattern 2: CSS Icon Rail Sidebar

**What:** A narrow fixed-position sidebar (~52px wide) on the left edge containing vertically-stacked icon links with tooltips.

**When to use:** When you need persistent navigation with minimal screen space impact.

**CSS approach:**

```css
.sidebar-rail {
    position: fixed;
    top: 0;
    left: 0;
    width: 52px;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 1rem;
    gap: 0.25rem;
    background: var(--bg-surface);
    border-right: 1px solid var(--border-dim);
    z-index: 50;
}

.sidebar-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    border: 1px solid transparent;
    transition: all 0.2s ease;
    position: relative;
}

.sidebar-icon:hover {
    color: var(--neon-cyan);
    border-color: var(--border-dim);
    background: rgba(90, 158, 170, 0.08);
}

.sidebar-icon.active {
    color: var(--neon-cyan);
    border-color: var(--neon-cyan);
    background: rgba(90, 158, 170, 0.1);
    box-shadow: 0 0 8px var(--neon-cyan-glow);
}

/* Tooltip on hover (CSS-only) */
.sidebar-icon::after {
    content: attr(title);
    position: absolute;
    left: calc(100% + 8px);
    top: 50%;
    transform: translateY(-50%);
    padding: 0.25rem 0.5rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border-dim);
    color: var(--text-primary);
    font-family: 'Orbitron', sans-serif;
    font-size: 0.65rem;
    letter-spacing: 0.1em;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.15s ease;
    z-index: 100;
}

.sidebar-icon:hover::after {
    opacity: 1;
}

/* Main content offset */
.main-content {
    margin-left: 52px;
}
```

**Key insight:** The sidebar uses `position: fixed` so it stays visible during scroll. The main content area uses `margin-left: 52px` to avoid overlap. For the graph page (which is `overflow: hidden`), the graph container simply gets the margin.

### Pattern 3: Active Page Highlighting via Route Context

**What:** Each FastAPI route handler passes `current_page` as a template context variable. The base template uses Jinja2 conditionals to add the `active` class.

**When to use:** Server-side rendered pages where navigation state is known at render time.

**Example (FastAPI side):**

```python
@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"current_page": "graph"})

@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "history.html", {"current_page": "history"})
```

**Why not JavaScript-based highlighting:** The URL is known server-side at render time. Doing it in Jinja2 means the active state is correct on first paint -- no flash of wrong state. It's also simpler and matches the "no new JS framework" constraint.

### Anti-Patterns to Avoid

- **Don't use JavaScript for active-page detection:** Parsing `window.location.pathname` client-side to set sidebar active state causes a flash-of-unstyled-content. The server already knows which page it's rendering.
- **Don't duplicate sidebar HTML in each template:** The entire point of template inheritance is to define the sidebar once in base.html.
- **Don't use `{% include %}` for the page layout:** Include is for partial fragments. Template inheritance (`{% extends %}`) is the correct pattern for defining the overall page skeleton.
- **Don't give the sidebar a sliding/hamburger behavior:** The spec says persistent icon rail, always visible. No toggle needed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Template inheritance | Custom HTML concatenation | Jinja2 `{% extends %}` / `{% block %}` | Built-in, well-tested, standard approach |
| Tooltip on hover | JavaScript tooltip library | CSS `::after` pseudo-element with `attr(title)` | Zero JS, works everywhere, sufficient for icon rail |
| Active page state | Client-side URL parsing | Server-side `current_page` template variable | No FOUC, simpler, more reliable |
| Theme persistence | Custom state management | Existing `localStorage.setItem('theme', ...)` pattern | Already implemented and working in all templates |

**Key insight:** Everything needed for this phase is already in the stack. The work is restructuring, not adding.

## Common Pitfalls

### Pitfall 1: Graph Page Layout Breaks When Adding Sidebar Margin

**What goes wrong:** The graph page (index.html) uses `overflow: hidden` on body and the D3.js SVG fills the entire viewport. Adding `margin-left: 52px` on `.main-content` can break the SVG sizing if the graph code measures `container.clientWidth` before the margin is applied.

**Why it happens:** The `LatticeGraph` class calls `container.clientWidth` during `setupSVG()`. If the layout hasn't settled or the margin changes the available width, the SVG size may be wrong.

**How to avoid:** Ensure the graph container div already has the correct width (accounting for sidebar) before graph.js initializes. Since `DOMContentLoaded` fires after CSS is applied, the margin should be in effect. But verify the `resize` handler also accounts for the sidebar width.

**Warning signs:** Graph SVG overflows the viewport to the right, or there's a gap on the right side.

### Pitfall 2: Duplicated Theme Toggle Logic

**What goes wrong:** All 4 templates have their own theme toggle JavaScript. When moving to base.html, you must consolidate this into one script block. If a child template still includes its own theme toggle code, you get duplicate event listeners.

**Why it happens:** Copy-paste inheritance in the current templates. Each independently loads and reads `localStorage('theme')`.

**How to avoid:** Move the theme toggle script to base.html (in a `{% block scripts %}` or after the sidebar). Remove duplicate code from child templates. The existing pattern of reading `localStorage('theme')` on page load and toggling `dark`/`light` classes works fine -- just put it in one place.

**Warning signs:** Theme toggle requires two clicks, or theme doesn't persist between page loads.

### Pitfall 3: asset_live.html Has a Different Header Pattern

**What goes wrong:** The `asset_live.html` template uses a compact custom header (`.live-header`) instead of the shared header used by index.html, history.html, and asset_detail.html. It was designed as a popup window, not a full page.

**Why it happens:** v1.0 designed asset_live as a popup window opened via `window.open()`. The compact header was intentional for a smaller window.

**How to avoid:** In Phase 4, asset_live.html should still extend base.html and use the sidebar, but it can override the header block with its own compact version. The key decision: does asset_live keep its compact header within the sidebar layout, or does it adopt the standard header? Given that v2.0 replaces popups with full-page navigation, asset_live should adopt the standard sidebar layout. However, the asset_live page is actually being **refactored into a full page** in Phase 5, so Phase 4 can simply add the sidebar to it as-is.

**Warning signs:** Sidebar appears on some pages but not asset_live, or asset_live has both the sidebar and the old compact header in a broken layout.

### Pitfall 4: Corner Decorations Z-Index Conflicts with Sidebar

**What goes wrong:** The `.corner-decor` elements are `position: fixed` with `z-index: 20`. The sidebar is also `position: fixed`. If the sidebar has a lower z-index, corner decorations appear on top of it. If higher, the left-side corner decorations may be hidden behind the sidebar.

**Why it happens:** Both elements occupy the same screen space (left edge).

**How to avoid:** Give the sidebar `z-index: 50` (matching the current header z-index). Adjust the left-side corner decorations to be offset by the sidebar width (left: 62px instead of 10px) or accept that they sit behind the sidebar.

**Warning signs:** Corner decorations overlap the sidebar icons, or disappear unexpectedly.

### Pitfall 5: Cache Busting on styles.css

**What goes wrong:** The current templates reference `styles.css?v=9`. If you add sidebar CSS to styles.css but don't bump the version, browsers may serve the cached version without the sidebar styles.

**Why it happens:** Browser caching of static assets.

**How to avoid:** Bump the cache buster version number when modifying styles.css (e.g., `?v=10`). Since base.html will be the single source for the stylesheet link, you only need to change it in one place.

**Warning signs:** Sidebar renders without styles, or styles appear only after hard-refreshing.

## Code Examples

### Example 1: FastAPI Route Handler with current_page Context

```python
# In routes.py - create_router()
@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"current_page": "graph"})

@router.get("/asset/{key:path}/live", response_class=HTMLResponse)
async def asset_live(request: Request, key: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "asset_live.html",
        {"asset_key": key, "current_page": "graph"},  # live is a sub-page of graph
    )

@router.get("/asset/{key:path}", response_class=HTMLResponse)
async def asset_detail(request: Request, key: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "asset_detail.html",
        {"asset_key": key, "current_page": "history"},  # asset detail is under history
    )

# In routes_history.py - create_history_router()
@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "history.html", {"current_page": "history"})
```

### Example 2: Sidebar Icon SVGs Matching Design Language

The project uses inline SVGs throughout. Three icons are needed:

1. **Graph/Home** -- The existing lattice logo SVG (4 connected squares) already defined in the header
2. **Active Runs** -- A play/activity icon (e.g., running figure or pulse line)
3. **Run History** -- A clock/history icon

```html
{# Graph icon (reuse lattice logo) #}
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
    <rect x="2" y="2" width="8" height="8" rx="1"/>
    <rect x="14" y="2" width="8" height="8" rx="1"/>
    <rect x="2" y="14" width="8" height="8" rx="1"/>
    <rect x="14" y="14" width="8" height="8" rx="1"/>
    <line x1="10" y1="6" x2="14" y2="6"/>
    <line x1="6" y1="10" x2="6" y2="14"/>
</svg>

{# Active Runs icon (activity/pulse) #}
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
</svg>

{# Run History icon (clock) #}
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
    <circle cx="12" cy="12" r="10"/>
    <polyline points="12 6 12 12 16 14"/>
</svg>
```

### Example 3: Sidebar Styling Matching Design System

```css
/* Add to styles.css */

/* ============================================
   SIDEBAR RAIL NAVIGATION
   ============================================ */

.sidebar-rail {
    position: fixed;
    top: 0;
    left: 0;
    width: 52px;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 1rem;
    gap: 0.25rem;
    background: var(--bg-surface);
    border-right: 1px solid var(--border-dim);
    z-index: 50;
}

.sidebar-rail::before {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 1px;
    height: 100%;
    background: linear-gradient(
        to bottom,
        transparent,
        var(--border-glow) 20%,
        var(--border-glow) 80%,
        transparent
    );
}

.sidebar-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    border: 1px solid transparent;
    text-decoration: none;
    transition: all 0.2s ease;
    clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
}

.sidebar-icon:hover {
    color: var(--neon-cyan);
    border-color: var(--border-dim);
    background: rgba(90, 158, 170, 0.08);
}

.sidebar-icon.active {
    color: var(--neon-cyan);
    border-color: var(--neon-cyan);
    background: rgba(90, 158, 170, 0.1);
    box-shadow: 0 0 8px var(--neon-cyan-glow);
}

/* CSS-only tooltip */
.sidebar-icon[title]::after {
    content: attr(title);
    position: absolute;
    left: calc(100% + 12px);
    top: 50%;
    transform: translateY(-50%);
    padding: 0.3rem 0.6rem;
    background: var(--bg-elevated);
    border: 1px solid var(--border-dim);
    color: var(--text-primary);
    font-family: 'Orbitron', sans-serif;
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.15s ease;
    z-index: 100;
}

.sidebar-icon:hover::after {
    opacity: 1;
}

/* Main content offset for sidebar */
.main-content {
    margin-left: 52px;
}
```

### Example 4: Base Template Block Structure

```html
{# base.html - block zones #}

{% block title %}        {# Page title after "LATTICE // " #}
{% block head_extra %}   {# Extra <style> tags for page-specific CSS #}
{% block body_class %}   {# Extra body classes (e.g., for graph page) #}
{% block content %}      {# Main page content #}
{% block scripts %}      {# Page-specific <script> tags #}
```

This gives child templates the ability to:
- Set the page title
- Add page-specific CSS without touching the shared head
- Add body classes (the graph page needs no scrollbar, other pages need `overflow: auto`)
- Define their main content
- Include page-specific JavaScript

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Standalone HTML pages with duplicated headers | Jinja2 template inheritance | v2.0 (this phase) | Single source of truth for shared structure |
| Top-right nav links (GRAPH / HISTORY) | Left sidebar icon rail | v2.0 (this phase) | Always-visible navigation, room for future items |
| Popup windows for asset monitoring | Full-page navigation with sidebar | v2.0 (this phase) | Better UX, standard browser navigation |

**Deprecated/outdated:**
- The top-right `<nav>` with `GRAPH` and `HISTORY` links will be replaced by sidebar icons
- The per-page header duplication will be eliminated by base.html

## Open Questions

1. **Should the header be in base.html or remain page-specific?**
   - What we know: index.html has a header with logo, nav links, and node count. history.html and asset_detail.html have similar headers. asset_live.html has a different compact header.
   - What's unclear: Should the header be consolidated into base.html, or should each page keep its own header via a `{% block header %}` override?
   - Recommendation: Put a default header in base.html (with the logo and title). The graph page can override it to add node count and relayout button. asset_live.html can override it with its compact version. This eliminates ~50 lines of duplication per template.

2. **Where does the "Active Runs" sidebar link go in Phase 4?**
   - What we know: Phase 4 requires 3 sidebar icons (graph, active runs, history). But the Active Runs page doesn't exist until Phase 5.
   - What's unclear: Should the "Active Runs" icon link to an existing page or be a placeholder?
   - Recommendation: Link the Active Runs icon to `/runs` and create a minimal placeholder page that says "Coming in Phase 5" or redirect to `/`. This satisfies SIDE-01 (3 icons present) without blocking on Phase 5. Alternatively, link it to `/` (graph page) temporarily and update in Phase 5.

3. **What happens to the right-side detail sidebar on the graph page?**
   - What we know: index.html has a right-side sliding sidebar (`#sidebar`) for showing asset details when a node is clicked. The new left-side sidebar rail is for navigation.
   - What's unclear: Do both sidebars coexist?
   - Recommendation: Yes, they coexist. The left sidebar rail is for navigation (always visible, 52px). The right sidebar is for asset details (slides in on click, 384px). They serve different purposes and don't conflict.

## Sources

### Primary (HIGH confidence)

- **Codebase analysis** (4 HTML templates, styles.css, routes.py, routes_history.py, app.py, graph.js) - Read and analyzed all existing templates, route handlers, and static assets
- **Jinja2 3.1 documentation** - Template inheritance is a core, stable feature since Jinja2 1.0; `{% extends %}`, `{% block %}`, template context variables are all standard and well-documented
- **Project planning docs** (.planning/ROADMAP.md, .planning/REQUIREMENTS.md) - Read requirements SIDE-01, SIDE-02, SIDE-03 and success criteria

### Secondary (MEDIUM confidence)

- **CSS icon rail pattern** - Widely used pattern (VS Code, Discord, Slack sidebar rails). Implementation is straightforward CSS (`position: fixed`, `flex-direction: column`, `width: 48-56px`)
- **CSS-only tooltips** - Standard pattern using `::after` pseudo-element with `content: attr(title)`. Works in all modern browsers.

### Tertiary (LOW confidence)

- None. All findings are based on direct codebase analysis and established patterns.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using existing Jinja2 + CSS, no new dependencies
- Architecture: HIGH - Template inheritance is well-understood; sidebar is standard CSS
- Pitfalls: HIGH - Identified from direct analysis of the 4 existing templates and their quirks

**Research date:** 2026-02-07
**Valid until:** 2026-03-07 (stable -- no external dependencies to go stale)
