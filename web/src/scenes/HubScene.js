/**
 * @fileoverview HubScene — The Master 3D Animated Hub.
 * Matches the specialist orbital core design with rotating wireframe sphere,
 * glowing orbital rings, floating 3D glass cards, and starfield particles.
 * @module scenes/HubScene
 */

import * as THREE from 'three';
import { isReducedMotion } from '../accessibility.js';

export const AGENTS = [
  {
    id: 'agent_galaxy',
    tag: 'AGENT 04',
    title: 'Debugger',
    subtitle: 'Reads the stack trace, finds the real cause.',
    color: '#eab308',
    glow: 'rgba(234, 179, 8, 0.4)',
    scene: 'commit_galaxy',
    pythonAction: 'commit_galaxy',
  },
  {
    id: 'agent_reviewer',
    tag: 'AGENT 03',
    title: 'Code Reviewer',
    subtitle: 'Reviews your diff like a staff engineer.',
    color: '#00e5ff',
    glow: 'rgba(0, 229, 255, 0.45)',
    scene: 'architecture',
    pythonAction: 'architecture',
  },
  {
    id: 'agent_security',
    tag: 'AGENT 02',
    title: 'Security Inspector',
    subtitle: 'Finds leaked keys and risky changes before you push.',
    color: '#f85149',
    glow: 'rgba(248, 81, 73, 0.45)',
    scene: 'security_map',
    pythonAction: 'security_map',
  },
  {
    id: 'agent_drafter',
    tag: 'AGENT 01',
    title: 'Commit Drafter',
    subtitle: 'Turns a diff into clean Conventional Commits.',
    color: '#3fb950',
    glow: 'rgba(63, 185, 80, 0.4)',
    scene: 'diff_comparator',
    pythonAction: 'git_desktop',
  },
  {
    id: 'agent_coach',
    tag: 'AGENT 05',
    title: 'Productivity Coach',
    subtitle: 'Reads your sessions and protects your focus.',
    color: '#a855f7',
    glow: 'rgba(168, 85, 247, 0.45)',
    scene: 'health_globe',
    pythonAction: 'overview',
  },
  {
    id: 'agent_analytics',
    tag: 'AGENT 06',
    title: 'Analytics Analyst',
    subtitle: 'Turns commit history into a readable story.',
    color: '#38bdf8',
    glow: 'rgba(56, 189, 248, 0.4)',
    scene: 'analytics',
    pythonAction: 'analytics',
  },
  {
    id: 'agent_topology',
    tag: 'AGENT 07',
    title: 'Feature Strategist',
    subtitle: 'Aligns pull requests with project roadmaps.',
    color: '#ec4899',
    glow: 'rgba(236, 72, 153, 0.4)',
    scene: 'device_topology',
    pythonAction: 'fleet',
  },
];

export default class HubScene {
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

    // Three.js Core elements
    this.coreMesh = null;
    this.ringMesh = null;
    this.starField = null;

    // DOM Overlays for 3D Cards
    this.hubRoot = null;
    this.stageEl = null;
    this.cardElements = [];

    // Orbital physics
    this.orbitAngle = 0;
    this.orbitSpeed = 0.15;
    this.isHoveringCard = false;
    this.radiusX = 480;
    this.radiusZ = 280;
    this.tiltY = 40;
  }

  async init() {
    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;

    // 1. WebGL Scene & Camera
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x050811);
    this.scene.fog = new THREE.FogExp2(0x050811, 0.0018);

    this.camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 2000);
    this.camera.position.set(0, 30, 140);
    this.camera.lookAt(0, 0, 0);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.container.appendChild(this.renderer.domElement);

    // 2. Build 3D Geometric Central Core (Geodesic / Icosahedron)
    this._buildCenterCore();

    // 3. Ambient Star Particles
    this._buildStarField();

    // 4. Mount 3D Specialist Cards DOM overlay
    this._buildDOMHub();
  }

  _buildCenterCore() {
    const group = new THREE.Group();

    // Wireframe Icosahedron Sphere in vibrant violet
    const geo = new THREE.IcosahedronGeometry(18, 2);
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0xa855f7,
      wireframe: true,
      transparent: true,
      opacity: 0.85,
    });
    this.coreMesh = new THREE.Mesh(geo, wireMat);
    group.add(this.coreMesh);

    // Inner glowing sphere core
    const innerGeo = new THREE.IcosahedronGeometry(12, 1);
    const innerMat = new THREE.MeshBasicMaterial({
      color: 0x8b5cf6,
      wireframe: false,
      transparent: true,
      opacity: 0.25,
    });
    const innerSphere = new THREE.Mesh(innerGeo, innerMat);
    group.add(innerSphere);

    // Outer cyan orbital ring
    const ringGeo = new THREE.TorusGeometry(32, 0.4, 16, 100);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x00e5ff,
      transparent: true,
      opacity: 0.8,
    });
    this.ringMesh = new THREE.Mesh(ringGeo, ringMat);
    this.ringMesh.rotation.x = Math.PI / 2.3;
    group.add(this.ringMesh);

    this.scene.add(group);
  }

  _buildStarField() {
    const count = 400;
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 800;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 500;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 800;
    }

    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const mat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 1.4,
      transparent: true,
      opacity: 0.5,
      blending: THREE.AdditiveBlending,
    });

    this.starField = new THREE.Points(geo, mat);
    this.scene.add(this.starField);
  }

  _buildDOMHub() {
    this.hubRoot = document.createElement('div');
    this.hubRoot.className = 'hub-root';

    // Header
    const header = document.createElement('div');
    header.className = 'hub-header';

    const pretitle = document.createElement('div');
    pretitle.className = 'hub-pretitle';
    pretitle.textContent = 'THE HUB';
    header.appendChild(pretitle);

    const h1 = document.createElement('h1');
    h1.className = 'hub-title';
    h1.textContent = 'Pick the specialist, not the chatbot.';
    header.appendChild(h1);

    const sub = document.createElement('p');
    sub.className = 'hub-subtitle';
    sub.textContent = 'Seven agents orbit the same core. Each one has its own expertise, its own memory and its own output format, so you stop prompting and start shipping.';
    header.appendChild(sub);

    this.hubRoot.appendChild(header);

    // 3D Perspective Stage
    const stageContainer = document.createElement('div');
    stageContainer.className = 'hub-stage-container';

    this.stageEl = document.createElement('div');
    this.stageEl.className = 'hub-stage';
    stageContainer.appendChild(this.stageEl);
    this.hubRoot.appendChild(stageContainer);

    // Footer Pill
    const footer = document.createElement('div');
    footer.className = 'hub-footer';

    const pill = document.createElement('div');
    pill.className = 'hub-pill';

    const dot = document.createElement('span');
    dot.className = 'hub-pill-dot';
    pill.appendChild(dot);

    const pillText = document.createElement('span');
    pillText.textContent = 'HOVER AN AGENT · CLICK TO OPEN';
    pill.appendChild(pillText);

    footer.appendChild(pill);
    this.hubRoot.appendChild(footer);

    // Build the 7 Cards
    const total = AGENTS.length;
    AGENTS.forEach((agent, index) => {
      const card = document.createElement('div');
      card.className = 'hub-card';
      card.style.setProperty('--agent-color', agent.color);
      card.style.setProperty('--agent-glow', agent.glow);

      const topSection = document.createElement('div');

      const tagRow = document.createElement('div');
      tagRow.className = 'hub-card-tag-row';

      const bar = document.createElement('span');
      bar.className = 'hub-card-bar';
      tagRow.appendChild(bar);

      const tag = document.createElement('span');
      tag.className = 'hub-card-tag';
      tag.textContent = agent.tag;
      tagRow.appendChild(tag);
      topSection.appendChild(tagRow);

      const title = document.createElement('div');
      title.className = 'hub-card-title';
      title.textContent = agent.title;
      topSection.appendChild(title);

      const desc = document.createElement('p');
      desc.className = 'hub-card-desc';
      desc.textContent = agent.subtitle;
      topSection.appendChild(desc);

      card.appendChild(topSection);

      const action = document.createElement('div');
      action.className = 'hub-card-action';
      action.textContent = 'OPEN →';
      card.appendChild(action);

      // Hover events
      card.addEventListener('mouseenter', () => {
        this.isHoveringCard = true;
      });
      card.addEventListener('mouseleave', () => {
        this.isHoveringCard = false;
      });

      // Click to launch scene
      card.addEventListener('click', (e) => {
        e.stopPropagation();
        this._onSelectAgent(agent);
      });

      this.stageEl.appendChild(card);
      this.cardElements.push({
        element: card,
        agent,
        baseAngle: (index / total) * Math.PI * 2,
      });
    });

    this.container.appendChild(this.hubRoot);
  }

  _onSelectAgent(agent) {
    if (this.bridge) {
      this.bridge.send('agent_selected', {
        agent: agent.id,
        scene: agent.scene,
        action: agent.pythonAction,
      });
    }

    if (window.__sceneRouter__) {
      window.__sceneRouter__.switchScene(agent.scene);
    }
  }

  update(deltaTime = 0.016) {
    // 1. Central Core continuous rotation
    if (this.coreMesh) {
      this.coreMesh.rotation.y += 0.005;
      this.coreMesh.rotation.x += 0.002;
    }
    if (this.ringMesh) {
      this.ringMesh.rotation.z += 0.003;
    }
    if (this.starField && !isReducedMotion()) {
      this.starField.rotation.y += 0.0003;
    }

    // 2. Orbit motion of the 7 cards
    if (!isReducedMotion()) {
      const speed = this.isHoveringCard ? this.orbitSpeed * 0.15 : this.orbitSpeed;
      this.orbitAngle += speed * deltaTime;
    }

    // 3. Position cards along tilted 3D ellipse
    const currentAngle = this.orbitAngle;
    this.cardElements.forEach((item) => {
      const angle = item.baseAngle + currentAngle;
      const x = Math.sin(angle) * this.radiusX;
      const z = Math.cos(angle) * this.radiusZ;
      const y = Math.sin(angle) * this.tiltY + 20;

      // Depth sorting & perspective tilt
      // Cards closer to camera (z > 0) face slightly towards center
      const cardRotateY = -Math.sin(angle) * 14;
      const cardRotateX = Math.cos(angle) * 4;

      item.element.style.transform = `translate3d(${x}px, ${y}px, ${z}px) rotateY(${cardRotateY}deg) rotateX(${cardRotateX}deg)`;
      item.element.style.zIndex = String(Math.round(z + 1000));
      
      // Slight opacity dip for cards deep in the background
      const depthFactor = (z + this.radiusZ) / (this.radiusZ * 2);
      item.element.style.opacity = String(0.7 + depthFactor * 0.3);
    });

    // 4. Render WebGL
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }

  resize(width, height) {
    if (!this.camera || !this.renderer) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);

    // Responsive ellipse radius
    if (width < 900) {
      this.radiusX = width * 0.42;
      this.radiusZ = 200;
    } else {
      this.radiusX = 480;
      this.radiusZ = 280;
    }
  }

  dispose() {
    if (this.renderer && this.renderer.domElement.parentElement) {
      this.renderer.domElement.parentElement.removeChild(this.renderer.domElement);
    }
    if (this.hubRoot && this.hubRoot.parentElement) {
      this.hubRoot.parentElement.removeChild(this.hubRoot);
    }
    if (this.coreMesh) {
      this.coreMesh.geometry.dispose();
      this.coreMesh.material.dispose();
    }
    if (this.ringMesh) {
      this.ringMesh.geometry.dispose();
      this.ringMesh.material.dispose();
    }
    if (this.starField) {
      this.starField.geometry.dispose();
      this.starField.material.dispose();
    }
    if (this.renderer) this.renderer.dispose();
  }

  getFallbackHTML() {
    return `
      <div style="padding: 40px; text-align: center;">
        <h2>The Hub — Specialist Center</h2>
        <p>3D acceleration is disabled. Showing agent catalog.</p>
      </div>
    `;
  }
}
