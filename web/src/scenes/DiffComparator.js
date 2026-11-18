/**
 * @fileoverview DiffComparator — 3D Code Diff Comparator.
 * Visualizes original vs modified code versions as layered 3D planes with syntax and AST diff highlights.
 * @module scenes/DiffComparator
 */

import * as THREE from 'three';

export default class DiffComparator {
  /**
   * @param {HTMLElement} container
   * @param {object} bridge
   * @param {object} [options={}]
   */
  constructor(container, bridge, options = {}) {
    this.container = container;
    this.bridge = bridge;
    this.options = options;

    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.diffPlanes = [];
  }

  async init() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e17);

    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;

    this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    this.camera.position.set(0, 20, 80);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 0.7);
    this.scene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0x00e5ff, 0.8);
    dirLight.position.set(40, 60, 40);
    this.scene.add(dirLight);

    // Initial placeholder planes for dual-code comparison
    this._createPlanes();
  }

  _createPlanes() {
    const geo = new THREE.PlaneGeometry(36, 48);
    const matBefore = new THREE.MeshStandardMaterial({
      color: 0x161d30,
      roughness: 0.4,
      metalness: 0.2,
      side: THREE.DoubleSide,
    });
    const matAfter = new THREE.MeshStandardMaterial({
      color: 0x122538,
      roughness: 0.4,
      metalness: 0.2,
      side: THREE.DoubleSide,
    });

    const planeBefore = new THREE.Mesh(geo, matBefore);
    planeBefore.position.set(-22, 0, 0);
    const planeAfter = new THREE.Mesh(geo, matAfter);
    planeAfter.position.set(22, 0, 0);

    this.scene.add(planeBefore);
    this.scene.add(planeAfter);
    this.diffPlanes.push(planeBefore, planeAfter);
  }

  async loadData(payload) {
    // Populate diff data from Python backend
  }

  update(deltaTime = 0.016) {
    if (this.diffPlanes.length === 2) {
      this.diffPlanes[0].rotation.y = Math.sin(Date.now() * 0.001) * 0.04;
      this.diffPlanes[1].rotation.y = -Math.sin(Date.now() * 0.001) * 0.04;
    }
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }

  resize(width, height) {
    if (!this.camera || !this.renderer) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  dispose() {
    if (this.renderer && this.renderer.domElement.parentElement) {
      this.renderer.domElement.parentElement.removeChild(this.renderer.domElement);
    }
    for (const plane of this.diffPlanes) {
      plane.geometry.dispose();
      plane.material.dispose();
    }
    this.diffPlanes = [];
    if (this.renderer) this.renderer.dispose();
  }

  getFallbackHTML() {
    return `
      <div class="glass-panel" style="padding: 24px; margin: 20px;">
        <h2>Code Diff Comparator (2D Fallback)</h2>
        <p>Interactive 3D view is disabled. Visualizing side-by-side file changes.</p>
      </div>
    `;
  }
}
