/**
 * @fileoverview Main entry point for CommitMaster 3D WebView2 viewport.
 * Initializes bridge, themes, accessibility, and scene routing.
 */

import bridge from './bridge.js';
import './theme.js';
import { isReducedMotion, getPerformanceTier } from './accessibility.js';
import './styles/hub.css';

// Scene imports
import HubScene from './scenes/HubScene.js';
import CommitGalaxy from './scenes/CommitGalaxy.js';
import ArchitectureExplorer from './scenes/ArchitectureExplorer.js';
import SecurityMap from './scenes/SecurityMap.js';
import AnalyticsDashboard from './scenes/AnalyticsDashboard.js';
import AgentWorkflow from './scenes/AgentWorkflow.js';
import DeviceTopology from './scenes/DeviceTopology.js';
import DiffComparator from './scenes/DiffComparator.js';
import MergeSimulator from './scenes/MergeSimulator.js';
import HealthGlobe from './scenes/HealthGlobe.js';
import CommitTimeline from './scenes/CommitTimeline.js';
import WorkspaceSwitcher from './scenes/WorkspaceSwitcher.js';
import DeploymentPipeline from './scenes/DeploymentPipeline.js';

const SCENE_REGISTRY = {
  hub: HubScene,
  commit_galaxy: CommitGalaxy,
  architecture: ArchitectureExplorer,
  security_map: SecurityMap,
  analytics: AnalyticsDashboard,
  agent_workflow: AgentWorkflow,
  device_topology: DeviceTopology,
  diff_comparator: DiffComparator,
  merge_simulator: MergeSimulator,
  health_globe: HealthGlobe,
  commit_timeline: CommitTimeline,
  workspace_switcher: WorkspaceSwitcher,
  deployment_pipeline: DeploymentPipeline,
};

class SceneRouter {
  constructor() {
    this.sceneContainer = document.getElementById('scene-container');
    this.uiOverlay = document.getElementById('ui-overlay');
    this.fallbackContainer = document.getElementById('fallback-container');

    this.currentScene = null;
    this.currentSceneName = null;
    this.is3dEnabled = true;

    this.lastTime = performance.now();
    this.animationFrameId = null;

    this._bindBridgeEvents();
    this._bindWindowEvents();
    this._startLoop();

    // Default startup scene: check hash or default to 3D Hub
    const initialScene = window.location.hash.slice(1) || 'hub';
    this.switchScene(initialScene);
  }

  _bindBridgeEvents() {
    bridge.on('scene_switch', (payload) => {
      const name = typeof payload === 'string' ? payload : payload?.scene;
      if (name) this.switchScene(name, payload?.data);
    });

    bridge.on('scene_data', (payload) => {
      if (this.currentScene && typeof this.currentScene.loadData === 'function') {
        this.currentScene.loadData(payload);
      }
    });

    bridge.on('3d_toggle', (payload) => {
      this.is3dEnabled = Boolean(payload?.enabled ?? true);
      this._update3dVisibility();
    });

    // Notify Python that the web frontend is ready
    bridge.send('ready', {
      tier: getPerformanceTier(),
      reducedMotion: isReducedMotion(),
    });
  }

  _bindWindowEvents() {
    window.addEventListener('resize', () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      if (this.currentScene && typeof this.currentScene.resize === 'function') {
        this.currentScene.resize(width, height);
      }
    });
  }

  async switchScene(sceneName, initialData = null) {
    if (!SCENE_REGISTRY[sceneName]) {
      console.warn(`[SceneRouter] Unknown scene "${sceneName}". Falling back to commit_galaxy.`);
      sceneName = 'commit_galaxy';
    }

    if (this.currentSceneName === sceneName && this.currentScene) {
      if (initialData) await this.currentScene.loadData(initialData);
      return;
    }

    // Dispose old scene
    if (this.currentScene) {
      try {
        if (typeof this.currentScene.dispose === 'function') {
          this.currentScene.dispose();
        }
      } catch (err) {
        console.error('[SceneRouter] Error disposing scene:', err);
      }
      this.sceneContainer.replaceChildren();
      this.currentScene = null;
    }

    this.currentSceneName = sceneName;
    const SceneClass = SCENE_REGISTRY[sceneName];

    try {
      this.currentScene = new SceneClass(this.sceneContainer, bridge);
      await this.currentScene.init();

      if (initialData) {
        await this.currentScene.loadData(initialData);
      }

      this._update3dVisibility();

      bridge.send('scene_loaded', { scene: sceneName });
    } catch (err) {
      console.error(`[SceneRouter] Failed to initialize scene "${sceneName}":`, err);
      this.showFallback(`Failed to load 3D scene: ${err.message}`);
    }
  }

  _update3dVisibility() {
    if (this.is3dEnabled) {
      this.sceneContainer.style.display = 'block';
      this.fallbackContainer.style.display = 'none';
    } else {
      this.sceneContainer.style.display = 'none';
      this.fallbackContainer.style.display = 'block';
      this.fallbackContainer.replaceChildren();

      const wrap = document.createElement('div');
      wrap.className = 'glass-panel';
      wrap.style.padding = '24px';
      wrap.style.margin = '20px';

      const h = document.createElement('h2');
      h.textContent = `${(this.currentSceneName || 'Scene').replace('_', ' ').toUpperCase()} (2D Fallback)`;
      const p = document.createElement('p');
      p.textContent = '3D visualization is currently disabled. Interactive 2D fallback view active.';

      wrap.appendChild(h);
      wrap.appendChild(p);
      this.fallbackContainer.appendChild(wrap);
    }
  }

  showFallback(message) {
    this.sceneContainer.style.display = 'none';
    this.fallbackContainer.style.display = 'block';
    this.fallbackContainer.replaceChildren();

    const box = document.createElement('div');
    box.style.padding = '40px';
    box.style.textAlign = 'center';
    box.style.color = '#94a3b8';

    const h2 = document.createElement('h2');
    h2.style.color = '#e2e8f0';
    h2.textContent = '3D Acceleration Unavailable';

    const p = document.createElement('p');
    p.textContent = String(message || 'WebGL acceleration inactive.');

    box.appendChild(h2);
    box.appendChild(p);
    this.fallbackContainer.appendChild(box);
  }

  _startLoop() {
    const loop = (now) => {
      const deltaTime = (now - this.lastTime) / 1000;
      this.lastTime = now;

      if (this.is3dEnabled && this.currentScene && typeof this.currentScene.update === 'function') {
        this.currentScene.update(deltaTime);
      }

      this.animationFrameId = requestAnimationFrame(loop);
    };
    this.animationFrameId = requestAnimationFrame(loop);
  }

  dispose() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    if (this.currentScene && typeof this.currentScene.dispose === 'function') {
      this.currentScene.dispose();
    }
  }
}

// Initialize on DOM load
window.addEventListener('DOMContentLoaded', () => {
  window.__sceneRouter__ = new SceneRouter();
});
