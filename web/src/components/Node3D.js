/**
 * @module Node3D
 * @description Interactive 3D node representation for commits, files, devices, and agents.
 * Supports individual mesh interactivity or batching via InstancedMesh for high performance.
 */

import * as THREE from 'three';
import { getThemeColor } from '../theme.js';

export default class Node3D {
  /**
   * @param {object} config
   * @param {string|number} config.id
   * @param {string} [config.label]
   * @param {THREE.Vector3|{x:number, y:number, z:number}} [config.position]
   * @param {number} [config.radius=2]
   * @param {number|string} [config.color=0x00e5ff]
   * @param {number} [config.emissiveIntensity=0.4]
   * @param {object} [config.data={}]
   */
  constructor(config = {}) {
    this.id = config.id ?? THREE.MathUtils.generateUUID();
    this.label = config.label || '';
    this.data = config.data || {};
    this.radius = config.radius ?? 2;
    this.baseColor = new THREE.Color(config.color || 0x00e5ff);
    this.emissiveIntensity = config.emissiveIntensity ?? 0.4;

    this.position = new THREE.Vector3(
      config.position?.x ?? 0,
      config.position?.y ?? 0,
      config.position?.z ?? 0
    );

    this.mesh = this._createMesh();
    this.selectionRing = this._createSelectionRing();
    this.mesh.add(this.selectionRing);
    this.selectionRing.visible = false;

    this.isHovered = false;
    this.isSelected = false;
  }

  _createMesh() {
    const geometry = new THREE.SphereGeometry(this.radius, 24, 24);
    const material = new THREE.MeshStandardMaterial({
      color: this.baseColor,
      emissive: this.baseColor,
      emissiveIntensity: this.emissiveIntensity,
      roughness: 0.3,
      metalness: 0.8,
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.copy(this.position);
    mesh.userData = { node: this, id: this.id };
    return mesh;
  }

  _createSelectionRing() {
    const ringGeo = new THREE.RingGeometry(this.radius * 1.3, this.radius * 1.5, 32);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    return ring;
  }

  setHover(hovered) {
    if (this.isHovered === hovered) return;
    this.isHovered = hovered;

    const scale = hovered ? 1.25 : 1.0;
    this.mesh.scale.set(scale, scale, scale);

    const mat = this.mesh.material;
    if (mat) {
      mat.emissiveIntensity = hovered ? 0.9 : this.emissiveIntensity;
    }
  }

  setSelected(selected) {
    this.isSelected = selected;
    this.selectionRing.visible = selected;
  }

  setColor(color) {
    this.baseColor.set(color);
    if (this.mesh.material) {
      this.mesh.material.color.copy(this.baseColor);
      this.mesh.material.emissive.copy(this.baseColor);
    }
  }

  setPosition(x, y, z) {
    this.position.set(x, y, z);
    this.mesh.position.copy(this.position);
  }

  dispose() {
    if (this.mesh.geometry) this.mesh.geometry.dispose();
    if (this.mesh.material) this.mesh.material.dispose();
    if (this.selectionRing.geometry) this.selectionRing.geometry.dispose();
    if (this.selectionRing.material) this.selectionRing.material.dispose();
  }
}
