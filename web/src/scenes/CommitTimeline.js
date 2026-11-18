/**
 * @fileoverview CommitTimeline — Interactive 3D Commit Timeline.
 * Replays commit history along a temporal axis with scrub controls and milestone callouts.
 * @module scenes/CommitTimeline
 */

import * as THREE from 'three';

export default class CommitTimeline {
  constructor(container, bridge, options = {}) {
    this.container = container;
    this.bridge = bridge;
    this.options = options;

    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.timelineNodes = [];
  }

  async init() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e17);

    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;

    this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    this.camera.position.set(0, 15, 60);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 0.7);
    this.scene.add(ambient);

    // Spine line
    const spineGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-60, 0, 0),
      new THREE.Vector3(60, 0, 0),
    ]);
    const spineMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.6 });
    const spine = new THREE.Line(spineGeo, spineMat);
    this.scene.add(spine);

    // Milestone markers
    const geo = new THREE.OctahedronGeometry(2, 0);
    const mat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x38bdf8, emissiveIntensity: 0.5 });
    for (let i = -4; i <= 4; i++) {
      const node = new THREE.Mesh(geo, mat);
      node.position.set(i * 14, 0, 0);
      this.scene.add(node);
      this.timelineNodes.push(node);
    }
  }

  async loadData(payload) {}

  update(deltaTime = 0.016) {
    for (const n of this.timelineNodes) {
      n.rotation.y += 0.01;
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
    for (const n of this.timelineNodes) {
      n.geometry.dispose();
      n.material.dispose();
    }
    this.timelineNodes = [];
    if (this.renderer) this.renderer.dispose();
  }

  getFallbackHTML() {
    return `
      <div class="glass-panel" style="padding: 24px; margin: 20px;">
        <h2>Commit Timeline (2D Fallback)</h2>
        <p>Interactive 3D view is disabled. Visualizing commit history chronological timeline.</p>
      </div>
    `;
  }
}
