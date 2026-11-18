/**
 * @module CameraController
 * @description OrbitControls wrapper with GSAP-powered smooth flyTo animations,
 * damping, boundary limits, and full respect for reduced-motion preferences.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import gsap from 'gsap';
import { isReducedMotion } from '../accessibility.js';

export default class CameraController {
  /**
   * @param {THREE.Camera} camera
   * @param {HTMLElement} domElement
   * @param {object} [options={}]
   */
  constructor(camera, domElement, options = {}) {
    this.camera = camera;
    this.domElement = domElement;

    this.controls = new OrbitControls(camera, domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = options.dampingFactor ?? 0.05;
    this.controls.maxDistance = options.maxDistance ?? 1000;
    this.controls.minDistance = options.minDistance ?? 5;
    this.controls.maxPolarAngle = options.maxPolarAngle ?? Math.PI;

    this.defaultPosition = camera.position.clone();
    this.defaultTarget = this.controls.target.clone();

    this._activeTween = null;
  }

  /**
   * Update controls damping in the animation frame loop.
   */
  update() {
    this.controls.update();
  }

  /**
   * Smoothly move the camera and target to a new position.
   * @param {THREE.Vector3|{x:number, y:number, z:number}} position
   * @param {THREE.Vector3|{x:number, y:number, z:number}} [target]
   * @param {number} [duration=1.2]
   * @returns {Promise<void>}
   */
  flyTo(position, target = null, duration = 1.2) {
    if (this._activeTween) {
      this._activeTween.kill();
      this._activeTween = null;
    }

    const targetPos = target ? new THREE.Vector3(target.x, target.y, target.z) : this.controls.target;

    if (isReducedMotion()) {
      this.camera.position.set(position.x, position.y, position.z);
      this.controls.target.copy(targetPos);
      this.controls.update();
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      const camStart = {
        x: this.camera.position.x,
        y: this.camera.position.y,
        z: this.camera.position.z,
      };
      const targetStart = {
        x: this.controls.target.x,
        y: this.controls.target.y,
        z: this.controls.target.z,
      };

      this._activeTween = gsap.to(
        {},
        {
          duration,
          ease: 'power3.inOut',
          onUpdate: () => {
            const progress = this._activeTween.progress();
            this.camera.position.set(
              THREE.MathUtils.lerp(camStart.x, position.x, progress),
              THREE.MathUtils.lerp(camStart.y, position.y, progress),
              THREE.MathUtils.lerp(camStart.z, position.z, progress)
            );
            this.controls.target.set(
              THREE.MathUtils.lerp(targetStart.x, targetPos.x, progress),
              THREE.MathUtils.lerp(targetStart.y, targetPos.y, progress),
              THREE.MathUtils.lerp(targetStart.z, targetPos.z, progress)
            );
            this.controls.update();
          },
          onComplete: () => {
            this._activeTween = null;
            resolve();
          },
        }
      );
    });
  }

  /**
   * Reset the camera to its initial transform.
   * @param {number} [duration=1.0]
   */
  reset(duration = 1.0) {
    return this.flyTo(this.defaultPosition, this.defaultTarget, duration);
  }

  /**
   * Clean up controls and active tweens.
   */
  dispose() {
    if (this._activeTween) {
      this._activeTween.kill();
    }
    this.controls.dispose();
  }
}
