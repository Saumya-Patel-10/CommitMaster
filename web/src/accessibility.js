/**
 * @module accessibility
 * @description Tracks reduced-motion preference and performance tier, applies
 * data-attributes to `<html>` for CSS, and detects WebGL capabilities.
 */

import { on, send } from './bridge.js';

/* ------------------------------------------------------------------ */
/*  State                                                              */
/* ------------------------------------------------------------------ */

/** @type {boolean} */
let reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

/** @type {'high'|'medium'|'low'} */
let performanceTier = 'high';

/** @type {boolean} */
let webglAvailable = true;

/** @type {object|null} WebGL capability snapshot */
let glCapabilities = null;

/* ------------------------------------------------------------------ */
/*  DOM attribute sync                                                 */
/* ------------------------------------------------------------------ */

/**
 * Write current accessibility state onto `<html>` attributes so CSS can react.
 */
function syncAttributes() {
  const html = document.documentElement;
  html.setAttribute('data-reduced-motion', String(reducedMotion));
  html.setAttribute('data-perf-tier', performanceTier);
}

/* ------------------------------------------------------------------ */
/*  Bridge handler                                                     */
/* ------------------------------------------------------------------ */

/**
 * Handle `accessibility_update` from the Python host.
 * @param {object} payload
 * @param {boolean}  [payload.reducedMotion]
 * @param {'high'|'medium'|'low'} [payload.performanceTier]
 */
function handleAccessibilityUpdate(payload) {
  if (!payload || typeof payload !== 'object') return;

  if (typeof payload.reducedMotion === 'boolean') {
    reducedMotion = payload.reducedMotion;
  }
  if (['high', 'medium', 'low'].includes(payload.performanceTier)) {
    performanceTier = payload.performanceTier;
  }

  syncAttributes();
}

/* ------------------------------------------------------------------ */
/*  WebGL detection                                                    */
/* ------------------------------------------------------------------ */

/**
 * Probe WebGL support and cache capabilities.
 * @returns {{ available: boolean, capabilities: object|null }}
 */
function detectWebGL() {
  try {
    const canvas = document.createElement('canvas');
    const gl =
      canvas.getContext('webgl2') ||
      canvas.getContext('webgl') ||
      canvas.getContext('experimental-webgl');

    if (!gl) {
      webglAvailable = false;
      glCapabilities = null;
      return { available: false, capabilities: null };
    }

    glCapabilities = {
      maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      maxCubeMapSize: gl.getParameter(gl.MAX_CUBE_MAP_TEXTURE_SIZE),
      maxRenderbufferSize: gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),
      maxVertexAttribs: gl.getParameter(gl.MAX_VERTEX_ATTRIBS),
      maxVaryingVectors: gl.getParameter(gl.MAX_VARYING_VECTORS),
      maxVertexTextureImageUnits: gl.getParameter(gl.MAX_VERTEX_TEXTURE_IMAGE_UNITS),
      maxTextureImageUnits: gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS),
      renderer: gl.getParameter(gl.RENDERER),
      vendor: gl.getParameter(gl.VENDOR),
    };

    // Auto-detect performance tier from GPU info
    const renderer = (glCapabilities.renderer || '').toLowerCase();
    if (
      renderer.includes('intel') ||
      renderer.includes('mesa') ||
      renderer.includes('swiftshader') ||
      renderer.includes('llvmpipe')
    ) {
      if (performanceTier === 'high') {
        performanceTier = 'medium';
      }
    }

    webglAvailable = true;
    return { available: true, capabilities: glCapabilities };
  } catch {
    webglAvailable = false;
    glCapabilities = null;
    return { available: false, capabilities: null };
  }
}

/**
 * Update capabilities from a live Three.js renderer.
 * @param {import('three').WebGLRenderer} renderer
 */
export function updateFromRenderer(renderer) {
  if (!renderer?.capabilities) return;

  const caps = renderer.capabilities;
  glCapabilities = {
    ...glCapabilities,
    maxTextures: caps.maxTextures,
    maxVertexTextures: caps.maxVertexTextures,
    maxTextureSize: caps.maxTextureSize,
    maxCubemapSize: caps.maxCubemapSize,
    maxAnisotropy: renderer.capabilities.getMaxAnisotropy?.() ?? 1,
    isWebGL2: caps.isWebGL2,
    supportsInstancing: true, // Three.js >=0.130 always supports instancing
  };

  // Downgrade tier if instancing is weak
  if (caps.maxVertexTextures < 4 && performanceTier === 'high') {
    performanceTier = 'medium';
    syncAttributes();
  }
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

/**
 * Whether animations should be suppressed.
 * @returns {boolean}
 */
export function isReducedMotion() {
  return reducedMotion;
}

/**
 * Current performance tier.
 * @returns {'high'|'medium'|'low'}
 */
export function getPerformanceTier() {
  return performanceTier;
}

/**
 * Whether WebGL is available.
 * @returns {boolean}
 */
export function isWebGLAvailable() {
  return webglAvailable;
}

/**
 * Cached WebGL capabilities.
 * @returns {object|null}
 */
export function getGLCapabilities() {
  return glCapabilities;
}

/**
 * Trigger fallback mode — hides the 3D container and shows the 2D fallback.
 */
export function activateFallback() {
  const scene = document.getElementById('scene-container');
  const fallback = document.getElementById('fallback-container');
  if (scene) scene.style.display = 'none';
  if (fallback) fallback.style.display = 'block';
  send('fallback_activated', { reason: webglAvailable ? 'performance' : 'no_webgl' });
}

/**
 * Initialize the accessibility module.
 */
export function initAccessibility() {
  // Listen to OS-level motion preference changes
  const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  if (mq) {
    reducedMotion = mq.matches;
    mq.addEventListener('change', (e) => {
      reducedMotion = e.matches;
      syncAttributes();
    });
  }

  // Detect WebGL
  const { available } = detectWebGL();
  if (!available) {
    activateFallback();
  }

  // Bridge updates from Python
  on('accessibility_update', handleAccessibilityUpdate);

  // Apply initial attributes
  syncAttributes();
}

export default {
  isReducedMotion,
  getPerformanceTier,
  isWebGLAvailable,
  getGLCapabilities,
  updateFromRenderer,
  activateFallback,
  initAccessibility,
};
