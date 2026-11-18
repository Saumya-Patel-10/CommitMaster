/**
 * @module bridge
 * @description Python ↔ JavaScript message bridge for CommitMaster WebView2.
 *
 * Detects whether the app is running inside a WebView2 host (window.chrome.webview)
 * or in a standalone browser (dev mode). In dev mode messages are logged to the
 * console and mock responses can be injected.
 *
 * Message format:
 * ```
 * { type: string, action?: string, payload?: any, requestId?: string }
 * ```
 */

/** @type {boolean} */
const isWebView2 = Boolean(window.chrome?.webview);

/** @type {Map<string, Set<function>>} */
const listeners = new Map();

/** @type {Map<string, function>} pending request/response callbacks keyed by requestId */
const pendingRequests = new Map();

/** @type {number} auto-incrementing request counter */
let requestCounter = 0;

/* ------------------------------------------------------------------ */
/*  Incoming message handler                                           */
/* ------------------------------------------------------------------ */

/**
 * Route an incoming message to registered listeners.
 * @param {object} data - Parsed message object.
 */
function handleIncoming(data) {
  if (!data || typeof data !== 'object') return;

  const { type, requestId } = data;

  // Resolve pending request/response if applicable
  if (requestId && pendingRequests.has(requestId)) {
    const resolve = pendingRequests.get(requestId);
    pendingRequests.delete(requestId);
    resolve(data.payload);
  }

  // Dispatch to `on` listeners
  if (type && listeners.has(type)) {
    for (const cb of listeners.get(type)) {
      try {
        cb(data.payload, data);
      } catch (err) {
        console.error(`[bridge] handler error for "${type}":`, err);
      }
    }
  }
}

// Wire up the WebView2 message channel and pywebview fallback
if (isWebView2) {
  window.chrome.webview.addEventListener('message', (event) => {
    handleIncoming(event.data);
  });
} else {
  // Dev-mode: listen for window messages (useful with postMessage from DevTools)
  window.addEventListener('message', (event) => {
    if (event.source !== window) return;
    handleIncoming(event.data);
  });

  console.info(
    '%c[bridge] Running in dev or standalone mode.',
    'color: #00e5ff; font-weight: bold;',
  );
}

// Global direct invocation hook from Python (evaluate_js)
window.__bridge_receive__ = function(data) {
  let parsed = data;
  if (typeof data === 'string') {
    try { parsed = JSON.parse(data); } catch (e) { parsed = data; }
  }
  handleIncoming(parsed);
};

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

/**
 * Send a message to the Python host.
 * @param {string} type   - Message type identifier.
 * @param {*}      [payload] - Arbitrary payload data.
 */
export function send(type, payload) {
  const message = { type, payload };

  if (isWebView2) {
    window.chrome.webview.postMessage(message);
  } else if (window.pywebview && window.pywebview.api && window.pywebview.api.send_message) {
    window.pywebview.api.send_message(JSON.stringify(message));
  } else {
    console.log('%c[bridge → python]', 'color: #a855f7;', message);
  }
}

/**
 * Register a handler for a given message type from Python.
 * @param {string}   type     - Message type to listen for.
 * @param {function} callback - `(payload, fullMessage) => void`
 */
export function on(type, callback) {
  if (!listeners.has(type)) {
    listeners.set(type, new Set());
  }
  listeners.get(type).add(callback);
}

/**
 * Remove a previously registered handler.
 * @param {string}   type     - Message type.
 * @param {function} callback - The exact function reference passed to `on`.
 */
export function off(type, callback) {
  if (listeners.has(type)) {
    listeners.get(type).delete(callback);
  }
}

/**
 * Register a one-shot handler that auto-removes after the first call.
 * @param {string}   type     - Message type.
 * @param {function} callback - `(payload, fullMessage) => void`
 */
export function once(type, callback) {
  /** @param {*} args */
  const wrapper = (...args) => {
    off(type, wrapper);
    callback(...args);
  };
  on(type, wrapper);
}

/**
 * Send a request to Python and wait for a response with a matching `requestId`.
 * @param {string} type      - Message type.
 * @param {*}      [payload] - Payload data.
 * @param {number} [timeout=5000] - Timeout in milliseconds.
 * @returns {Promise<*>} Resolves with the response payload.
 */
export function request(type, payload, timeout = 5000) {
  const requestId = `req_${++requestCounter}_${Date.now()}`;
  const message = { type, payload, requestId };

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pendingRequests.delete(requestId);
      reject(new Error(`[bridge] request "${type}" timed out after ${timeout}ms`));
    }, timeout);

    pendingRequests.set(requestId, (result) => {
      clearTimeout(timer);
      resolve(result);
    });

    if (isWebView2) {
      window.chrome.webview.postMessage(message);
    } else if (window.pywebview && window.pywebview.api && window.pywebview.api.send_message) {
      window.pywebview.api.send_message(JSON.stringify(message));
    } else {
      console.log('%c[bridge → python] (request)', 'color: #a855f7;', message);
      // Dev mode: auto-resolve with null after a short delay
      setTimeout(() => {
        if (pendingRequests.has(requestId)) {
          const res = pendingRequests.get(requestId);
          pendingRequests.delete(requestId);
          clearTimeout(timer);
          res(null);
        }
      }, 200);
    }
  });
}

/**
 * Simulate an incoming message (useful for dev/testing).
 * @param {object} data - Full message object.
 */
export function simulateIncoming(data) {
  handleIncoming(data);
}

/**
 * Whether the bridge is connected to a WebView2 host.
 * @returns {boolean}
 */
export function isConnected() {
  return isWebView2;
}

/** Default export bundles the full API */
export default { send, on, off, once, request, simulateIncoming, isConnected };
