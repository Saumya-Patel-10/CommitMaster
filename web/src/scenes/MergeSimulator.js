/**
 * @fileoverview MergeSimulator — 3D Branch Merge Simulator.
 * Interactive preview of branch relationships, merge impacts, and conflict predictions.
 * @module scenes/MergeSimulator
 */

import * as THREE from 'three';

export default class MergeSimulator {
  constructor(container, bridge, options = {}) {
    this.container = container;
    this.bridge = bridge;
    this.options = options;

    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.branchNodes = [];
  }

  async init() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e17);

    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;

    this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    this.camera.position.set(0, 30, 90);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 0.7);
    this.scene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0xa855f7, 0.8);
    dirLight.position.set(30, 50, 40);
    this.scene.add(dirLight);

    this._createDemoBranches();
  }

  _createDemoBranches() {
    const geo = new THREE.SphereGeometry(2.5, 20, 20);
    const matBase = new THREE.MeshStandardMaterial({ color: 0x00e5ff, emissive: 0x00e5ff, emissiveIntensity: 0.3 });
    const matBranch = new THREE.MeshStandardMaterial({ color: 0xa855f7, emissive: 0xa855f7, emissiveIntensity: 0.3 });

    for (let i = -3; i <= 3; i++) {
      const baseNode = new THREE.Mesh(geo, matBase);
      baseNode.position.set(i * 12, 0, 0);
      this.scene.add(baseNode);
      this.branchNodes.push(baseNode);
    }

    for (let i = 0; i <= 3; i++) {
      const branch = new THREE.Mesh(geo, matBranch);
      branch.position.set(i * 12, 14, 0);
      this.scene.add(branch);
      this.branchNodes.push(branch);
    }
  }

  async loadData(payload) {}

  update(deltaTime = 0.016) {
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
    for (const n of this.branchNodes) {
      n.geometry.dispose();
      n.material.dispose();
    }
    this.branchNodes = [];
    if (this.renderer) this.renderer.dispose();
  }

  getFallbackHTML() {
    return `
      <div class="glass-panel" style="padding: 24px; margin: 20px;">
        <h2>Branch Merge Simulator (2D Fallback)</h2>
        <p>Interactive 3D view is disabled. Visualizing branch merge simulation tabularly.</p>
      </div>
    `;
  }
}
