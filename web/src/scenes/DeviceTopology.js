/**
 * @fileoverview DeviceTopology — Device network topology.
 * Displays connected devices and network nodes as a 3D force-directed
 * graph with animated data-flow particles along the edges.
 * @module scenes/DeviceTopology
 */

import * as THREE from 'three';

/**
 * Device network topology scene.
 */
export default class DeviceTopology {
  /**
   * @param {HTMLElement} container — DOM element to mount the renderer into.
   * @param {object} bridge — Python↔JS message bridge.
   * @param {object} [options={}] — Optional configuration overrides.
   */
  constructor(container, bridge, options = {}) {
    /** @type {HTMLElement} */
    this.container = container;
    /** @type {object} */
    this.bridge = bridge;
    /** @type {object} */
    this.options = options;

    /** @type {THREE.WebGLRenderer|null} */
    this.renderer = null;
    /** @type {THREE.Scene|null} */
    this.scene = null;
    /** @type {THREE.PerspectiveCamera|null} */
    this.camera = null;
  }

  /**
   * Initialise the Three.js scene, camera, and renderer.
   * @returns {Promise<void>}
   */
  async init() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e17);

    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;

    this.camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 1500);
    this.camera.position.set(0, 60, 120);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);
  }

  /**
   * Receive device topology data from the Python backend.
   * @param {object} payload — Network nodes and links payload.
   * @returns {Promise<void>}
   */
  async loadData(payload) {
    // Stub — will build force-directed topology graph
  }

  /**
   * Per-frame animation tick.
   * @param {number} deltaTime — Seconds since the last frame.
   */
  update(deltaTime) {
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }

  /**
   * Handle viewport resize.
   * @param {number} width — New width in pixels.
   * @param {number} height — New height in pixels.
   */
  resize(width, height) {
    if (this.camera) {
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
    }
    if (this.renderer) {
      this.renderer.setSize(width, height);
    }
  }

  /**
   * Dispose of all Three.js resources and remove the renderer DOM element.
   */
  dispose() {
    if (this.renderer) {
      this.renderer.dispose();
      this.renderer.domElement.remove();
      this.renderer = null;
    }
    this.scene = null;
    this.camera = null;
  }

  /**
   * Return 2D HTML fallback when WebGL is unavailable.
   * @returns {string} Fallback HTML string.
   */
  getFallbackHTML() {
    return '<div class="fallback-scene"><h2>Device Topology</h2><p>3D topology view requires WebGL.</p></div>';
  }
}
