/**
 * @module Edge3D
 * @description Connection lines between 3D nodes with animated particle flow,
 * curved paths, and dashed styling for merges and dependencies.
 */

import * as THREE from 'three';
import { isReducedMotion } from '../accessibility.js';

export default class Edge3D {
  /**
   * @param {object} config
   * @param {THREE.Vector3} config.source
   * @param {THREE.Vector3} config.target
   * @param {number|string} [config.color=0x38bdf8]
   * @param {boolean} [config.curved=true]
   * @param {boolean} [config.dashed=false]
   * @param {boolean} [config.animated=true]
   * @param {number} [config.particleCount=3]
   */
  constructor(config = {}) {
    this.source = config.source;
    this.target = config.target;
    this.color = new THREE.Color(config.color || 0x38bdf8);
    this.curved = config.curved ?? true;
    this.dashed = config.dashed ?? false;
    this.animated = config.animated ?? true;
    this.particleCount = config.particleCount ?? 3;

    this.group = new THREE.Group();
    this.curve = this._buildCurve();
    this.line = this._buildLine();
    this.group.add(this.line);

    this.particles = [];
    if (this.animated && !isReducedMotion()) {
      this._buildParticles();
    }
  }

  _buildCurve() {
    if (!this.curved) {
      return new THREE.LineCurve3(this.source, this.target);
    }
    const mid = new THREE.Vector3().addVectors(this.source, this.target).multiplyScalar(0.5);
    const distance = this.source.distanceTo(this.target);
    mid.y += distance * 0.15; // Subtle upward arc
    return new THREE.QuadraticBezierCurve3(this.source, this.target, mid);
  }

  _buildLine() {
    const points = this.curve.getPoints(32);
    const geometry = new THREE.BufferGeometry().setFromPoints(points);

    let material;
    if (this.dashed) {
      material = new THREE.LineDashedMaterial({
        color: this.color,
        dashSize: 2,
        gapSize: 1,
        transparent: true,
        opacity: 0.7,
      });
    } else {
      material = new THREE.LineBasicMaterial({
        color: this.color,
        transparent: true,
        opacity: 0.6,
      });
    }

    const line = new THREE.Line(geometry, material);
    if (this.dashed) {
      line.computeLineDistances();
    }
    return line;
  }

  _buildParticles() {
    const geo = new THREE.SphereGeometry(0.35, 8, 8);
    const mat = new THREE.MeshBasicMaterial({
      color: this.color,
      transparent: true,
      opacity: 0.9,
    });

    for (let i = 0; i < this.particleCount; i++) {
      const p = new THREE.Mesh(geo, mat);
      const initialT = i / this.particleCount;
      const pt = this.curve.getPoint(initialT);
      p.position.copy(pt);
      p.userData = { t: initialT, speed: 0.005 + (i % 2) * 0.002 };
      this.group.add(p);
      this.particles.push(p);
    }
  }

  update(deltaTime = 0.016) {
    if (isReducedMotion() || this.particles.length === 0) return;

    for (const p of this.particles) {
      p.userData.t = (p.userData.t + p.userData.speed * (deltaTime * 60)) % 1.0;
      const pt = this.curve.getPoint(p.userData.t);
      p.position.copy(pt);
    }
  }

  dispose() {
    if (this.line.geometry) this.line.geometry.dispose();
    if (this.line.material) this.line.material.dispose();
    for (const p of this.particles) {
      if (p.geometry) p.geometry.dispose();
      if (p.material) p.material.dispose();
    }
  }
}
