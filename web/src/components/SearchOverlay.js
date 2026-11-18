/**
 * @module SearchOverlay
 * @description Quick search and filter overlay across 3D nodes (commits, files, devices).
 * Keyboard shortcut: Ctrl+F to open, Escape to dismiss.
 * Safe DOM creation — zero innerHTML XSS exploit vectors.
 */

export default class SearchOverlay {
  /**
   * @param {HTMLElement} parentContainer
   * @param {Function} onSelect - Callback when an item is chosen.
   */
  constructor(parentContainer, onSelect) {
    this.parent = parentContainer;
    this.onSelect = onSelect;
    this.items = [];

    this.element = this._createDOM();
    this.parent.appendChild(this.element);

    this._bindEvents();
  }

  _createDOM() {
    const el = document.createElement('div');
    el.className = 'glass-panel search-overlay-container';
    el.style.display = 'none';

    const wrapper = document.createElement('div');
    wrapper.className = 'search-input-wrapper';

    const icon = document.createElement('span');
    icon.className = 'search-icon';
    icon.textContent = '🔍';
    wrapper.appendChild(icon);

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'search-input';
    input.placeholder = 'Search nodes, commits, or files... (Ctrl+F)';
    wrapper.appendChild(input);

    const clearBtn = document.createElement('button');
    clearBtn.className = 'search-clear-btn';
    clearBtn.textContent = '×';
    wrapper.appendChild(clearBtn);

    el.appendChild(wrapper);

    const resultsList = document.createElement('div');
    resultsList.className = 'search-results-list';
    el.appendChild(resultsList);

    return el;
  }

  _bindEvents() {
    const input = this.element.querySelector('.search-input');
    const clearBtn = this.element.querySelector('.search-clear-btn');

    input.addEventListener('input', (e) => this._filter(e.target.value));
    clearBtn.addEventListener('click', () => {
      input.value = '';
      this._filter('');
    });

    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        this.toggle();
      } else if (e.key === 'Escape' && this.isVisible()) {
        this.hide();
      }
    });
  }

  setItems(items) {
    this.items = items || [];
  }

  _filter(query) {
    const list = this.element.querySelector('.search-results-list');
    list.replaceChildren();
    const q = query.trim().toLowerCase();

    if (!q) {
      list.style.display = 'none';
      return;
    }

    const matches = this.items.filter((item) => {
      const text = `${item.label || ''} ${item.id || ''} ${item.subtitle || ''}`.toLowerCase();
      return text.includes(q);
    }).slice(0, 8);

    if (matches.length === 0) {
      const noRes = document.createElement('div');
      noRes.className = 'search-no-results';
      noRes.textContent = 'No matching nodes found';
      list.appendChild(noRes);
      list.style.display = 'block';
      return;
    }

    list.style.display = 'block';
    for (const match of matches) {
      const row = document.createElement('div');
      row.className = 'search-result-item';

      const titleSpan = document.createElement('span');
      titleSpan.className = 'search-item-title';
      titleSpan.textContent = match.label || match.id;
      row.appendChild(titleSpan);

      if (match.subtitle) {
        const subSpan = document.createElement('span');
        subSpan.className = 'search-item-sub';
        subSpan.textContent = match.subtitle;
        row.appendChild(subSpan);
      }

      row.addEventListener('click', () => {
        if (this.onSelect) this.onSelect(match);
        this.hide();
      });
      list.appendChild(row);
    }
  }

  show() {
    this.element.style.display = 'block';
    const input = this.element.querySelector('.search-input');
    input.focus();
    input.select();
  }

  hide() {
    this.element.style.display = 'none';
    const list = this.element.querySelector('.search-results-list');
    list.style.display = 'none';
  }

  toggle() {
    if (this.isVisible()) this.hide();
    else this.show();
  }

  isVisible() {
    return this.element.style.display !== 'none';
  }

  dispose() {
    if (this.element && this.element.parentElement) {
      this.element.parentElement.removeChild(this.element);
    }
  }
}
