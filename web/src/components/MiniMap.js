/**
 * @module MiniMap
 * @description 2D radar/minimap inset showing spatial node distribution and camera frustum orientation.
 */

export default class MiniMap {
  /**
   * @param {HTMLElement} parentContainer
   * @param {object} [options]
   */
  constructor(parentContainer, options = {}) {
    this.parent = parentContainer;
    this.size = options.size ?? 140;
    this.nodePositions = [];
    this.cameraPos = { x: 0, z: 0 };

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'glass-panel minimap-canvas';
    this.canvas.width = this.size;
    this.canvas.height = this.size;
    this.ctx = this.canvas.getContext('2d');

    this.parent.appendChild(this.canvas);
  }

  setNodes(positions) {
    this.nodePositions = positions || [];
    this.render();
  }

  updateCamera(camX, camZ) {
    this.cameraPos.x = camX;
    this.cameraPos.z = camZ;
    this.render();
  }

  render() {
    const ctx = this.ctx;
    const s = this.size;
    const half = s / 2;

    ctx.clearRect(0, 0, s, s);

    // Background circle
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(half, half, half - 4, 0, Math.PI * 2);
    ctx.stroke();

    // Crosshairs
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.beginPath();
    ctx.moveTo(half, 4);
    ctx.lineTo(half, s - 4);
    ctx.moveTo(4, half);
    ctx.lineTo(s - 4, half);
    ctx.stroke();

    // Nodes
    const scale = 0.35;
    ctx.fillStyle = 'rgba(0, 229, 255, 0.7)';
    for (const p of this.nodePositions) {
      const nx = half + (p.x || 0) * scale;
      const ny = half + (p.z || 0) * scale;
      if (nx >= 2 && nx <= s - 2 && ny >= 2 && ny <= s - 2) {
        ctx.fillRect(nx, ny, 2, 2);
      }
    }

    // Camera indicator
    const cx = half + this.cameraPos.x * scale;
    const cy = half + this.cameraPos.z * scale;
    ctx.fillStyle = '#ff0055';
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  dispose() {
    if (this.canvas && this.canvas.parentElement) {
      this.canvas.parentElement.removeChild(this.canvas);
    }
  }
}
