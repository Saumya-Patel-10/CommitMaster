/**
 * @module ParticleSystem
 * @description Ambient background particle field for depth and futuristic aesthetic.
 * Automatically throttles particle density on lower performance tiers and disables motion for reduced-motion.
 */

import * as THREE from 'three';
import { isReducedMotion, getPerformanceTier } from '../accessibility.js';
import { getAccentColor } from '../theme.js';

export default class ParticleSystem {
  /**
   * @param {THREE.Scene} scene
   * @param {object} [options]
   */
  constructor(scene, options = {}) {
    this.scene = scene;
    this.boxSize = options.boxSize ?? 600;

    const tier = getPerformanceTier();
    this.count = tier === 'low' ? 0 : tier === 'medium' ? 150 : options.count ?? 450;

    this.points = null;
    if (this.count > 0) {
      this._init();
    }
  }

  _init() {
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(this.count * 3);
    const speeds = new Float32Array(this.count);

    for (let i = 0; i < this.count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * this.boxSize;
      positions[i * 3 + 1] = (Math.random() - 0.5) * this.boxSize;
      positions[i * 3 + 2] = (Math.random() - 0.5) * this.boxSize;
      speeds[i] = 0.2 + Math.random() * 0.4;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.PointsMaterial({
      color: new THREE.Color(getAccentColor()),
      size: 1.8,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
    });

    this.points = new THREE.Points(geometry, material);
    this.points.userData = { speeds };
    this.scene.add(this.points);
  }

  update(deltaTime = 0.016) {
    if (!this.points || isReducedMotion()) return;

    const positions = this.points.geometry.attributes.position.array;
    const speeds = this.points.userData.speeds;
    const half = this.boxSize / 2;

    for (let i = 0; i < this.count; i++) {
      positions[i * 3 + 1] += speeds[i] * (deltaTime * 30);
      if (positions[i * 3 + 1] > half) {
        positions[i * 3 + 1] = -half;
      }
    }

    this.points.geometry.attributes.position.needsUpdate = true;
    this.points.rotation.y += 0.0003;
  }

  updateColor(hexColor) {
    if (this.points && this.points.material) {
      this.points.material.color.set(hexColor);
    }
  }

  dispose() {
    if (this.points) {
      this.scene.remove(this.points);
      if (this.points.geometry) this.points.geometry.dispose();
      if (this.points.material) this.points.material.dispose();
      this.points = null;
    }
  }
}
