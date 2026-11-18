/**
 * @fileoverview DeploymentPipeline — 3D Deployment Pipeline Visualization.
 * Interactive 3D conveyor/stepper showing build, test, scan, approval, and deployment stages.
 * @module scenes/DeploymentPipeline
 */

import * as THREE from 'three';

export default class DeploymentPipeline {
  constructor(container, bridge, options = {}) {
    this.container = container;
    this.bridge = bridge;
    this.options = options;

    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.stageBoxes = [];
  }

  async init() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e17);

    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;

    this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    this.camera.position.set(0, 20, 70);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 0.7);
    this.scene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0x00e5ff, 0.9);
    dirLight.position.set(30, 40, 30);
    this.scene.add(dirLight);

    // 5 Stages: Build -> Test -> Scan -> Approval -> Deploy
    const stages = ['Build', 'Test', 'Security Scan', 'Approval', 'Deploy'];
    const boxGeo = new THREE.BoxGeometry(10, 8, 4);

    for (let i = 0; i < stages.length; i++) {
      const mat = new THREE.MeshStandardMaterial({
        color: 0x161d30,
        roughness: 0.3,
        metalness: 0.6,
      });
      const box = new THREE.Mesh(boxGeo, mat);
      box.position.set((i - 2) * 16, 0, 0);
      this.scene.add(box);
      this.stageBoxes.push(box);
    }
  }

  async loadData(payload) {}

  update(deltaTime = 0.016) {
    for (let i = 0; i < this.stageBoxes.length; i++) {
      this.stageBoxes[i].position.y = Math.sin(Date.now() * 0.002 + i * 0.5) * 0.8;
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
    for (const box of this.stageBoxes) {
      box.geometry.dispose();
      box.material.dispose();
    }
    this.stageBoxes = [];
    if (this.renderer) this.renderer.dispose();
  }

  getFallbackHTML() {
    return `
      <div class="glass-panel" style="padding: 24px; margin: 20px;">
        <h2>Deployment Pipeline (2D Fallback)</h2>
        <p>Interactive 3D view is disabled. Visualizing CI/CD deployment pipeline stages.</p>
      </div>
    `;
  }
}
