/**
 * @module theme
 * @description Receives theme tokens from the Python host and applies them as
 * CSS custom properties on `:root`. Also exposes getters for use in JS/Three.js.
 */

import { on } from './bridge.js';

/* ------------------------------------------------------------------ */
/*  Mapping: Python color name → CSS custom property                   */
/* ------------------------------------------------------------------ */

/** @type {Record<string, string>} */
const COLOR_MAP = {
  bg_darkest:     '--cm-bg-darkest',
  bg_dark:        '--cm-bg-dark',
  bg_medium:      '--cm-bg-medium',
  bg_card:        '--cm-bg-card',
  bg_card_hover:  '--cm-bg-card-hover',
  accent:         '--cm-accent',
  text_primary:   '--cm-text-primary',
  text_secondary: '--cm-text-secondary',
  text_muted:     '--cm-text-muted',
  border:         '--cm-border',
};

/** @type {Record<string, string>} current resolved values */
const currentColors = {
  '--cm-bg-darkest':     '#0a0e17',
  '--cm-bg-dark':        '#0d1322',
  '--cm-bg-medium':      '#131a2e',
  '--cm-bg-card':        '#161d30',
  '--cm-bg-card-hover':  '#1a2338',
  '--cm-accent':         '#00e5ff',
  '--cm-text-primary':   '#e2e8f0',
  '--cm-text-secondary': '#94a3b8',
  '--cm-text-muted':     '#64748b',
  '--cm-border':         'rgba(255,255,255,0.08)',
};

/** @type {Set<function>} */
const changeCallbacks = new Set();

/* ------------------------------------------------------------------ */
/*  Internal helpers                                                   */
/* ------------------------------------------------------------------ */

/**
 * Write all current colors to :root CSS custom properties.
 */
function applyToDOM() {
  const root = document.documentElement.style;
  for (const [prop, value] of Object.entries(currentColors)) {
    root.setProperty(prop, value);
  }
}

/**
 * Handle a `theme_update` message from Python.
 * @param {Record<string, string>} payload - Map of Python color names to hex values.
 */
function handleThemeUpdate(payload) {
  if (!payload || typeof payload !== 'object') return;

  for (const [pyName, cssVar] of Object.entries(COLOR_MAP)) {
    if (payload[pyName] != null) {
      currentColors[cssVar] = payload[pyName];
    }
  }

  applyToDOM();

  // Notify JS subscribers
  for (const cb of changeCallbacks) {
    try {
      cb({ ...currentColors });
    } catch (err) {
      console.error('[theme] change callback error:', err);
    }
  }
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

/**
 * Get the current value of a theme CSS custom property.
 * @param {string} name - CSS property name without `--cm-` prefix, e.g. `'accent'`.
 *                        Also accepts the full property name `'--cm-accent'`.
 * @returns {string} The current CSS color value.
 */
export function getThemeColor(name) {
  const key = name.startsWith('--cm-') ? name : `--cm-${name.replace(/_/g, '-')}`;
  return currentColors[key] ?? '';
}

/**
 * Get the current accent color.
 * @returns {string}
 */
export function getAccentColor() {
  return currentColors['--cm-accent'];
}

/**
 * Get the darkest background color (used for Three.js scene background).
 * @returns {string}
 */
export function getBackgroundColor() {
  return currentColors['--cm-bg-darkest'];
}

/**
 * Subscribe to theme changes.
 * @param {function} callback - `(colors: Record<string, string>) => void`
 * @returns {function} Unsubscribe function.
 */
export function onThemeChange(callback) {
  changeCallbacks.add(callback);
  return () => changeCallbacks.delete(callback);
}

/**
 * Initialize the theme module: apply defaults and start listening for updates.
 */
export function initTheme() {
  applyToDOM();
  on('theme_update', handleThemeUpdate);
}

export default { getThemeColor, getAccentColor, getBackgroundColor, onThemeChange, initTheme };
