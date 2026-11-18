/**
 * @module InfoPanel
 * @description Glassmorphic floating detail panel overlay.
 * Displays node metadata, security findings, or commit information with action buttons.
 * Safe DOM creation — zero innerHTML XSS exploit vectors.
 */

export default class InfoPanel {
  /**
   * @param {HTMLElement} parentContainer
   */
  constructor(parentContainer) {
    this.parent = parentContainer;
    this.element = this._createDOM();
    this.parent.appendChild(this.element);
    this.isVisible = false;
  }

  _createDOM() {
    const el = document.createElement('div');
    el.className = 'glass-panel info-panel-container';
    el.style.display = 'none';

    // Header container
    const header = document.createElement('div');
    header.className = 'info-panel-header';

    const titleGroup = document.createElement('div');
    titleGroup.className = 'info-panel-title-group';

    const badge = document.createElement('span');
    badge.className = 'info-panel-badge';
    badge.id = 'info-badge';
    titleGroup.appendChild(badge);

    const title = document.createElement('h3');
    title.className = 'info-panel-title';
    title.id = 'info-title';
    titleGroup.appendChild(title);
    header.appendChild(titleGroup);

    const closeBtn = document.createElement('button');
    closeBtn.className = 'info-panel-close';
    closeBtn.id = 'info-close';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.textContent = '×';
    closeBtn.addEventListener('click', () => this.hide());
    header.appendChild(closeBtn);

    el.appendChild(header);

    const subtitle = document.createElement('div');
    subtitle.className = 'info-panel-subtitle';
    subtitle.id = 'info-subtitle';
    el.appendChild(subtitle);

    const body = document.createElement('div');
    body.className = 'info-panel-body';
    body.id = 'info-body';
    el.appendChild(body);

    const actions = document.createElement('div');
    actions.className = 'info-panel-actions';
    actions.id = 'info-actions';
    el.appendChild(actions);

    return el;
  }

  /**
   * Show the panel with structured data.
   * @param {object} data
   * @param {string} data.title
   * @param {string} [data.badge]
   * @param {string} [data.badgeColor]
   * @param {string} [data.subtitle]
   * @param {Array<{label:string, value:string}>} [data.items]
   * @param {string} [data.description]
   * @param {Array<{label:string, onClick:Function, primary?:boolean}>} [data.actions]
   * @param {{x:number, y:number}} [screenPosition]
   */
  show(data, screenPosition = null) {
    const titleEl = this.element.querySelector('#info-title');
    const badgeEl = this.element.querySelector('#info-badge');
    const subEl = this.element.querySelector('#info-subtitle');
    const bodyEl = this.element.querySelector('#info-body');
    const actionsEl = this.element.querySelector('#info-actions');

    titleEl.textContent = data.title || 'Details';

    if (data.badge) {
      badgeEl.textContent = data.badge;
      badgeEl.style.display = 'inline-block';
      if (data.badgeColor) badgeEl.style.borderColor = data.badgeColor;
    } else {
      badgeEl.style.display = 'none';
    }

    subEl.textContent = data.subtitle || '';
    bodyEl.replaceChildren();

    if (data.items && data.items.length > 0) {
      const dl = document.createElement('dl');
      dl.className = 'info-panel-dl';
      for (const item of data.items) {
        const dt = document.createElement('dt');
        dt.textContent = item.label;
        const dd = document.createElement('dd');
        dd.textContent = item.value;
        dl.appendChild(dt);
        dl.appendChild(dd);
      }
      bodyEl.appendChild(dl);
    }

    if (data.description) {
      const desc = document.createElement('p');
      desc.className = 'info-panel-desc';
      desc.textContent = data.description;
      bodyEl.appendChild(desc);
    }

    actionsEl.replaceChildren();
    if (data.actions && data.actions.length > 0) {
      for (const act of data.actions) {
        const btn = document.createElement('button');
        btn.className = act.primary ? 'btn-primary' : 'btn-secondary';
        btn.textContent = act.label;
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          act.onClick();
        });
        actionsEl.appendChild(btn);
      }
    }

    if (screenPosition) {
      const x = Math.min(screenPosition.x + 20, window.innerWidth - 380);
      const y = Math.min(Math.max(screenPosition.y - 40, 20), window.innerHeight - 340);
      this.element.style.left = `${x}px`;
      this.element.style.top = `${y}px`;
      this.element.style.position = 'absolute';
    } else {
      this.element.style.right = '24px';
      this.element.style.top = '24px';
      this.element.style.left = 'auto';
      this.element.style.position = 'fixed';
    }

    this.element.style.display = 'block';
    this.isVisible = true;
  }

  hide() {
    this.element.style.display = 'none';
    this.isVisible = false;
  }

  dispose() {
    if (this.element && this.element.parentElement) {
      this.element.parentElement.removeChild(this.element);
    }
  }
}
