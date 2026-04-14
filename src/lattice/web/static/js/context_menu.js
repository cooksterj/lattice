/**
 * Shared right-click context menu for graph views.
 *
 * Each graph page (overview, asset detail, group detail) instantiates
 * one ContextMenu and calls `show(event, assetId)` from its D3
 * `contextmenu` handler.
 *
 * The menu DOM is expected to live in the page template with the IDs
 * referenced below; this class owns behavior only, not markup.
 */
class ContextMenu {
    /**
     * @param {object} options
     * @param {(targetId: string, includeDownstream: boolean) => void} options.onRun
     *     Invoked when the user clicks "Run + Downstream" or "Run Only This".
     * @param {() => boolean} [options.isRunning]
     *     Returns true when execution is in progress; disables the run buttons.
     * @param {(targetId: string) => void} [options.onViewDetails]
     *     Defaults to navigating to /asset/<id>.
     */
    constructor({onRun, isRunning, onViewDetails} = {}) {
        this.onRun = onRun ?? (() => {});
        this.isRunning = isRunning ?? (() => false);
        this.onViewDetails = onViewDetails ?? ((id) => {
            window.location.href = '/asset/' + encodeURIComponent(id);
        });

        this.menu = document.getElementById('context-menu');
        if (!this.menu) return;

        this._hide = () => this.menu.classList.remove('visible');
        this._onKeydown = (e) => { if (e.key === 'Escape') this._hide(); };

        document.addEventListener('click', this._hide);
        document.addEventListener('keydown', this._onKeydown);

        this._bindButton('ctx-run-downstream', true);
        this._bindButton('ctx-run-only', false);

        document.getElementById('ctx-view-details')?.addEventListener('click', (e) => {
            e.stopPropagation();
            const targetId = this.menu.dataset.targetId;
            if (targetId) this.onViewDetails(targetId);
            this._hide();
        });
    }

    _bindButton(id, includeDownstream) {
        document.getElementById(id)?.addEventListener('click', (e) => {
            e.stopPropagation();
            const targetId = this.menu.dataset.targetId;
            if (targetId) this.onRun(targetId, includeDownstream);
            this._hide();
        });
    }

    show(event, assetId) {
        if (!this.menu) return;

        this.menu.dataset.targetId = assetId;

        const targetEl = document.getElementById('context-menu-target');
        const displayName = assetId.includes('/') ? assetId.split('/').pop() : assetId;
        targetEl.textContent = displayName.toUpperCase();

        const running = this.isRunning();
        const runDown = document.getElementById('ctx-run-downstream');
        const runOnly = document.getElementById('ctx-run-only');
        if (runDown) runDown.disabled = running;
        if (runOnly) runOnly.disabled = running;

        const menuWidth = 260;
        const menuHeight = 300;
        let x = event.clientX;
        let y = event.clientY;
        if (x + menuWidth > window.innerWidth) x = window.innerWidth - menuWidth - 8;
        if (y + menuHeight > window.innerHeight) y = window.innerHeight - menuHeight - 8;
        this.menu.style.left = `${x}px`;
        this.menu.style.top = `${y}px`;
        this.menu.classList.add('visible');

        this._loadPreview(assetId);
    }

    _loadPreview(assetId) {
        const preview = document.getElementById('context-menu-preview');
        if (!preview) return;

        preview.replaceChildren(this._makePreviewMessage('LOADING PLAN...', 'context-menu-preview-loading'));

        fetch(`/api/plan?target=${encodeURIComponent(assetId)}&include_downstream=true`)
            .then(r => r.json())
            .then(data => {
                const steps = data.steps || [];
                if (steps.length === 0) {
                    preview.replaceChildren(this._makePreviewMessage('NO ASSETS'));
                    return;
                }
                preview.replaceChildren(this._makePreviewBody(assetId, steps));
            })
            .catch(() => {
                preview.replaceChildren(this._makePreviewMessage('FAILED TO LOAD'));
            });
    }

    _makePreviewMessage(text, className = 'context-menu-preview-title') {
        const div = document.createElement('div');
        div.className = className;
        div.textContent = text;
        return div;
    }

    _makePreviewBody(assetId, steps) {
        const wrapper = document.createDocumentFragment();

        const title = document.createElement('div');
        title.className = 'context-menu-preview-title';
        title.textContent = `EXECUTION PLAN (${steps.length})`;
        wrapper.appendChild(title);

        const list = document.createElement('div');
        list.className = 'context-menu-preview-list';
        for (const step of steps) {
            const row = document.createElement('div');
            row.className = 'context-menu-preview-asset';
            if (step.id === assetId) row.classList.add('is-target');
            row.textContent = step.id;
            list.appendChild(row);
        }
        wrapper.appendChild(list);
        return wrapper;
    }
}

window.ContextMenu = ContextMenu;
