/**
 * @module GraphLayout
 * @description Graph layout manager leveraging Graphology and deterministic layout algorithms.
 * Computes 3D coordinates for commit graphs, architecture topologies, and device networks.
 */

import Graph from 'graphology';

export default class GraphLayout {
  constructor() {
    this.graph = new Graph();
  }

  /**
   * Reset and populate the graph from raw nodes and edges.
   * @param {Array<{id:string|number, [key:string]:any}>} nodes
   * @param {Array<{source:string|number, target:string|number, [key:string]:any}>} edges
   */
  loadData(nodes = [], edges = []) {
    this.graph.clear();

    for (const n of nodes) {
      if (!this.graph.hasNode(String(n.id))) {
        this.graph.addNode(String(n.id), { ...n });
      }
    }

    for (const e of edges) {
      const src = String(e.source);
      const tgt = String(e.target);
      if (this.graph.hasNode(src) && this.graph.hasNode(tgt) && !this.graph.hasEdge(src, tgt)) {
        this.graph.addEdge(src, tgt, { ...e });
      }
    }
  }

  /**
   * Compute positions along a spiral or linear branch progression for commit histories.
   * @param {object} [options]
   * @param {number} [options.spacing=12]
   * @param {number} [options.branchSpread=25]
   * @returns {Map<string, {x:number, y:number, z:number}>}
   */
  computeCommitSpine(options = {}) {
    const spacing = options.spacing ?? 14;
    const branchSpread = options.branchSpread ?? 24;
    const positions = new Map();

    const branchOffsets = new Map();
    let branchCounter = 0;

    let index = 0;
    this.graph.forEachNode((nodeId, attr) => {
      const branch = attr.branch || 'main';
      if (!branchOffsets.has(branch)) {
        branchOffsets.set(branch, (branchCounter++ % 2 === 0 ? 1 : -1) * Math.ceil(branchCounter / 2) * branchSpread);
      }

      const x = branchOffsets.get(branch);
      const z = -index * spacing;
      const y = Math.sin(index * 0.4) * 4;

      positions.set(nodeId, { x, y, z });
      index++;
    });

    return positions;
  }

  /**
   * Compute hierarchical radial layout for codebase architecture.
   * @param {object} [options]
   * @param {number} [options.radius=60]
   * @returns {Map<string, {x:number, y:number, z:number}>}
   */
  computeRadialLayout(options = {}) {
    const baseRadius = options.radius ?? 60;
    const positions = new Map();
    const count = this.graph.order;

    let i = 0;
    this.graph.forEachNode((nodeId, attr) => {
      const phi = Math.acos(-1 + (2 * i) / Math.max(count, 1));
      const theta = Math.sqrt(count * Math.PI) * phi;

      const r = baseRadius * (attr.type === 'dir' ? 0.6 : attr.type === 'file' ? 1.0 : 1.3);
      const x = r * Math.cos(theta) * Math.sin(phi);
      const y = r * Math.sin(theta) * Math.sin(phi);
      const z = r * Math.cos(phi);

      positions.set(nodeId, { x, y, z });
      i++;
    });

    return positions;
  }

  /**
   * Compute force-directed 2.5D layout for network/device topology.
   * @returns {Map<string, {x:number, y:number, z:number}>}
   */
  computeTopologyLayout() {
    const positions = new Map();
    const count = this.graph.order;
    let i = 0;

    this.graph.forEachNode((nodeId, attr) => {
      const angle = (i / Math.max(count, 1)) * Math.PI * 2;
      const dist = 35 + (i % 3) * 15;
      const x = Math.cos(angle) * dist;
      const z = Math.sin(angle) * dist;
      const y = (attr.authorized ? 0 : -8);

      positions.set(nodeId, { x, y, z });
      i++;
    });

    return positions;
  }
}
