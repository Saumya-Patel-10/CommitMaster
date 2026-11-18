/**
 * @fileoverview HealthGlobe — AI Code Health Globe.
 * Rotatable 3D globe representing repository modules, health metrics, and technical debt indicators.
 * @module scenes/HealthGlobe
 */

import * as THREE from 'three';

export default class HealthGlobe {
  constructor(container, bridge, options = {}) {
    this.container = container;
    this.bridge = bridge;
    this.options = options;

    this.renderer = null;
    this.scene = null;
    this.camera = null;
    this.globe = null;
    this.clouds = null;
  }

  async init() {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0a0e17);

    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;

    this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    this.camera.position.set(0, 0, 75);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0x00e5ff, 1.2);
    dirLight.position.set(50, 40, 50);
    this.scene.add(dirLight);

    // Main wireframe/globe sphere
    const geo = new THREE.SphereGeometry(24, 36, 36);
    const mat = new THREE.MeshStandardMaterial({
      color: 0x161d30,
      roughness: 0.6,
      metalness: 0.5,
      wireframe: false,
    });
    this.globe = new THREE.Mesh(geo, mat);
    this.scene.add(this.globe);

    // Outer aura/wireframe
    const wireGeo = new THREE.SphereGeometry(24.5, 24, 24);
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0x00e5ff,
      wireframe: true,
      transparent: true,
      opacity: 0.25,
    });
    this.clouds = new THREE.Mesh(wireGeo, wireMat);
    this.scene.add(this.clouds);
  }

  async loadData(payload) {}

  update(deltaTime = 0.016) {
    if (this.globe) {
      this.globe.rotation.y += 0.002;
    }
    if (this.clouds) {
      this.clouds.rotation.y += 0.003;
      this.clouds.rotation.x += 0.001;
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
    if (this.globe) {
      this.globe.geometry.dispose();
      this.globe.material.dispose();
    }
    if (this.clouds) {
      this.clouds.geometry.dispose();
      this.clouds.material.dispose();
    }
    if (this.renderer) this.renderer.dispose();
  }

  getFallbackHTML() {
    return `
      <div class="glass-panel" style="padding: 24px; margin: 20px;">
        <h2>Code Health Globe (2D Fallback)</h2>
        <p>Interactive 3D view is disabled. Visualizing code health metrics.</p>
      </div>
    `;
  }
}
