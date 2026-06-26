/**
 * Smart Solar Plug — Firebase Real-Time Listener & Auth (Frontend)
 * Connects to Firebase RTDB and mirrors WebSocket updates.
 * Retrieves configuration dynamically from backend to keep keys secure.
 */

// API Endpoint configuration
const API_URL = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/live";
const SSE_URL = "http://localhost:8000/api/telemetry/stream";

let wsConnection = null;
let wsReconnectTimer = null;
let sseConnection = null;
let isFirebaseConnected = false;
let isWsConnected = false;
let isSseConnected = false;
let firebaseInitialized = false;

// ── Mock Firebase Fallback for Offline / Sandbox Testing ─────────────────────
if (typeof firebase === "undefined") {
  console.log("[Firebase] Sandbox or offline environment detected. Initializing mock auth system.");
  
  let currentMockUser = null;
  const mockAuthListeners = [];

  const savedUser = localStorage.getItem("mockUser");
  if (savedUser) {
    try {
      currentMockUser = JSON.parse(savedUser);
    } catch(e) {
      localStorage.removeItem("mockUser");
    }
  }

  const mockAuth = {
    signInWithEmailAndPassword: function(email, password) {
      currentMockUser = { email: email, uid: "mock-uid-123" };
      localStorage.setItem("mockUser", JSON.stringify(currentMockUser));
      setTimeout(() => {
        mockAuthListeners.forEach(fn => fn(currentMockUser));
      }, 50);
      return Promise.resolve({ user: currentMockUser });
    },
    createUserWithEmailAndPassword: function(email, password) {
      currentMockUser = { email: email, uid: "mock-uid-123" };
      localStorage.setItem("mockUser", JSON.stringify(currentMockUser));
      setTimeout(() => {
        mockAuthListeners.forEach(fn => fn(currentMockUser));
      }, 50);
      return Promise.resolve({ user: currentMockUser });
    },
    signOut: function() {
      currentMockUser = null;
      localStorage.removeItem("mockUser");
      setTimeout(() => {
        mockAuthListeners.forEach(fn => fn(null));
      }, 50);
      return Promise.resolve();
    },
    onAuthStateChanged: function(fn) {
      mockAuthListeners.push(fn);
      setTimeout(() => fn(currentMockUser), 50);
    },
    signInWithPopup: function(provider) {
      currentMockUser = { email: "google_mock@example.com", uid: "mock-uid-google" };
      localStorage.setItem("mockUser", JSON.stringify(currentMockUser));
      setTimeout(() => {
        mockAuthListeners.forEach(fn => fn(currentMockUser));
      }, 50);
      return Promise.resolve({ user: currentMockUser });
    }
  };

  mockAuth.GoogleAuthProvider = function() {
    this.providerId = "google.com";
  };

  window.firebase = {
    initializeApp: () => ({}),
    database: () => ({
      ref: () => ({
        on: () => {},
        off: () => {}
      })
    }),
    auth: () => mockAuth
  };
  window.firebase.auth.GoogleAuthProvider = mockAuth.GoogleAuthProvider;
}

// Callbacks registered by app.js
const dataListeners = [];
const authListeners = [];

let _lastDispatchTs = null; // For deduplication between WS + SSE

function onLiveData(fn) { dataListeners.push(fn); }
function onAuthStateChangedListener(fn) { authListeners.push(fn); }

function _dispatch(data) {
  // Deduplicate: skip if we already dispatched the same timestamp within 1s
  const ts = data.timestamp || null;
  if (ts && ts === _lastDispatchTs) return;
  _lastDispatchTs = ts;
  dataListeners.forEach(fn => {
    try { fn(data); } catch(e) { console.error("Listener error:", e); }
  });
}

function _dispatchAuth(user) {
  authListeners.forEach(fn => {
    try { fn(user); } catch(e) { console.error("Auth listener error:", e); }
  });
}

// ── WebSocket (primary live data channel) ────────────────────────────────────
function connectWebSocket() {
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) return;

  try {
    wsConnection = new WebSocket(WS_URL);

    wsConnection.onopen = () => {
      isWsConnected = true;
      console.log("[WS] Connected to backend.");
      updateConnectionStatus(true);
      if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
    };

    wsConnection.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === "ping") return; // ignore heartbeats
        _dispatch(data);
      } catch(e) { console.warn("[WS] Bad message:", e); }
    };

    wsConnection.onclose = () => {
      isWsConnected = false;
      if (!isSseConnected) updateConnectionStatus(false);
      console.warn("[WS] Disconnected. Reconnecting in 5s...");
      wsReconnectTimer = setTimeout(connectWebSocket, 5000);
    };

    wsConnection.onerror = (e) => {
      console.warn("[WS] Error:", e);
      isWsConnected = false;
      wsConnection.close();
    };

  } catch(e) {
    console.error("[WS] Failed to connect:", e);
    wsReconnectTimer = setTimeout(connectWebSocket, 5000);
  }
}

// ── SSE (Server-Sent Events) — browser-native auto-reconnect fallback ───────────
function connectSSE() {
  if (sseConnection) { sseConnection.close(); }

  try {
    sseConnection = new EventSource(SSE_URL);

    sseConnection.onopen = () => {
      isSseConnected = true;
      console.log("[SSE] Connected to backend stream.");
      updateConnectionStatus(true);
    };

    sseConnection.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === "ping") return; // ignore heartbeats
        // Only update UI if WebSocket hasn't already handled this (dedup by type check)
        _dispatch(data);
      } catch(e) { console.warn("[SSE] Bad message:", e); }
    };

    sseConnection.onerror = () => {
      isSseConnected = false;
      if (!isWsConnected) updateConnectionStatus(false);
      console.warn("[SSE] Connection error. Browser will auto-reconnect...");
      // EventSource auto-reconnects natively — no manual timer needed
    };

  } catch(e) {
    console.error("[SSE] Failed to connect:", e);
  }
}

// ── Firebase SDK (secondary, direct RTDB listener & authentication) ───────────
async function initFirebase() {
  try {
    if (typeof firebase === "undefined") {
      console.warn("[Firebase] SDK script not loaded yet. Retrying...");
      setTimeout(initFirebase, 500);
      return;
    }

    // 1. Fetch Firebase config from FastAPI backend
    console.log("[Firebase] Fetching config from background...");
    const resp = await fetch(`${API_URL}/api/config/firebase`);
    if (!resp.ok) {
      throw new Error(`Failed to load Firebase config: ${resp.statusText}`);
    }
    const config = await resp.json();
    console.log("[Firebase] Loaded config for project:", config.projectId);

    // 2. Initialize Firebase App
    const app = firebase.initializeApp(config);
    const db  = firebase.database(app);
    const auth = firebase.auth(app);
    firebaseInitialized = true;

    // 3. Listen for Telemetry Real-time Data
    const telRef = db.ref("/telemetry");
    telRef.on("value", (snapshot) => {
      const raw = snapshot.val();
      if (!raw) return;
      isFirebaseConnected = true;

      // Transform Firebase structure to flat format
      const env  = raw.environment  || {};
      const elec = raw.electrical   || {};
      const data = {
        type:            "telemetry",
        source:          "firebase-direct",
        timestamp:       new Date().toISOString(),
        light_intensity: env.light_intensity,
        temperature:     env.temperature,
        humidity:        env.humidity,
        voltage:         elec.voltage,
        current:         elec.current,
        power:           elec.power,
        energy:          elec.energy,
      };

      // Only dispatch if WebSocket is not providing data (fallback channel)
      if (!isWsConnected) { _dispatch(data); }
    });

    db.ref(".info/connected").on("value", (snap) => {
      isFirebaseConnected = !!snap.val();
      if (!isWsConnected) { updateConnectionStatus(isFirebaseConnected); }
    });

    // 4. Setup Auth State Listener
    auth.onAuthStateChanged((user) => {
      console.log("[Auth] State changed:", user ? user.email : "No user logged in.");
      _dispatchAuth(user);
    });

    console.log("[Firebase] RTDB and Auth SDK initialized successfully.");
  } catch(e) {
    console.error("[Firebase] Initialization error:", e);
    // Retry in 5s
    setTimeout(initFirebase, 5000);
  }
}

// ── Auth helper functions ────────────────────────────────────────────────────

function signInWithEmail(email, password) {
  if (!firebaseInitialized) return Promise.reject("Firebase not initialized yet.");
  return firebase.auth().signInWithEmailAndPassword(email, password);
}

function signUpWithEmail(email, password) {
  if (!firebaseInitialized) return Promise.reject("Firebase not initialized yet.");
  return firebase.auth().createUserWithEmailAndPassword(email, password);
}

function signInWithGoogle() {
  if (!firebaseInitialized) return Promise.reject("Firebase not initialized yet.");
  const provider = new firebase.auth.GoogleAuthProvider();
  return firebase.auth().signInWithPopup(provider);
}

function signOutUser() {
  if (!firebaseInitialized) return Promise.resolve();
  return firebase.auth().signOut();
}

// ── Connection Badge UI ──────────────────────────────────────────────────────
function updateConnectionStatus(connected) {
  const badge = document.getElementById("connectionBadge");
  const dot   = document.getElementById("connectionDot");
  const text  = document.getElementById("connectionText");
  if (!badge) return;

  if (connected) {
    badge.className = "connection-badge connected";
    dot.classList.add("pulse");
    text.textContent = "Live";
  } else {
    badge.className = "connection-badge disconnected";
    dot.classList.remove("pulse");
    text.textContent = "Offline";
  }
}

// ── Bootstrap Connections ────────────────────────────────────────────────────
function initConnections() {
  connectWebSocket();   // Fastest live channel
  connectSSE();         // Reliable browser-native fallback (auto-reconnects)
  initFirebase();       // Firebase RTDB listener + Auth
}
