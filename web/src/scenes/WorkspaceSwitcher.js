/**
 * @fileoverview WorkspaceSwitcher — 3D GitHub Account Workspace Switcher.
 * Visualizes personal, enterprise, and organization repositories in 3D carousels with auth badges.
 * @module scenes/WorkspaceSwitcher
 */

import * as THREE from 'three';

export default class WorkspaceSwitcher {
  constructor(container, bridge, options = {}) {
    this.container = container;
    this.bridge = bridge;
    this.options = options;

    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.accountPanels = [];
  }

  async init() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e17);

    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;

    this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    this.camera.position.set(0, 10, 60);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 0.8);
    this.scene.add(ambient);

    // Three workspace pedestal cards (e.g. Personal, Work, Org)
    const cardGeo = new THREE.BoxGeometry(16, 22, 1.5);
    const colors = [0x00e5ff, 0xbc8cff, 0x3fb950];

    for (let i = -1; i <= 1; i++) {
      const mat = new THREE.MeshStandardMaterial({
        color: 0x161d30,
        roughness: 0.3,
        metalness: 0.7,
      });
      const card = new THREE.Mesh(cardGeo, mat);
      card.position.set(i * 24, 0, 0);
      this.scene.add(card);
      this.accountPanels.push(card);
    }
  }

  async loadData(payload) {}

  update(deltaTime = 0.016) {
    for (let i = 0; i < this.accountPanels.length; i++) {
      this.accountPanels[i].rotation.y = Math.sin(Date.now() * 0.001 + i) * 0.05;
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
    for (const card of this.accountPanels) {
      card.geometry.dispose();
      card.material.dispose();
    }
    this.accountPanels = [];
    if (this.renderer) this.renderer.dispose();
  }

  getFallbackHTML() {
    return `
      <div class="glass-panel" style="padding: 24px; margin: 20px;">
        <h2>GitHub Account Switcher (2D Fallback)</h2>
        <p>Interactive 3D view is disabled. Visualizing connected GitHub workspaces.</p>
      </div>
    `;
  }
}
