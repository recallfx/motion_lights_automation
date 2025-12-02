/**
 * Reactive state store with WebSocket connection management.
 * Components subscribe to state changes via callbacks.
 */

class StateStore {
    constructor() {
        this._state = {};
        this._config = {};
        this._serverTimestamp = null;
        this._connected = false;
        this._ws = null;
        this._listeners = new Set();
        this._connectionListeners = new Set();
    }

    get state() { return this._state; }
    get config() { return this._config; }
    get serverTimestamp() { return this._serverTimestamp; }
    get connected() { return this._connected; }

    // Computed getters
    get currentState() { return this._state.current_state || 'standby'; }
    get timeInState() { return this._state.time_in_state || 0; }
    get lights() { return this._state.lights || {}; }
    get sensors() { return this._state.sensors || {}; }
    get timers() { return this._state.timers || {}; }
    get eventLog() { return this._state.event_log || []; }

    get lightData() {
        return Object.values(this.lights)[0] || { is_on: false, brightness_pct: 0 };
    }

    get motionData() {
        return Object.values(this.sensors).find(s => s.type === 'motion') || { state: false };
    }

    get overrideData() {
        return Object.values(this.sensors).find(s => s.type === 'override') || { state: false };
    }

    get motionActive() { return this.motionData.state; }
    get overrideActive() { return this.overrideData.state; }

    // Subscribe to state changes
    subscribe(callback) {
        this._listeners.add(callback);
        return () => this._listeners.delete(callback);
    }

    // Subscribe to connection changes
    subscribeConnection(callback) {
        this._connectionListeners.add(callback);
        return () => this._connectionListeners.delete(callback);
    }

    _notify() {
        this._listeners.forEach(cb => cb(this));
    }

    _notifyConnection() {
        this._connectionListeners.forEach(cb => cb(this._connected));
    }

    // WebSocket connection
    connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this._ws = new WebSocket(`${protocol}//${location.host}/ws`);

        this._ws.onopen = () => {
            this._connected = true;
            this._notifyConnection();
        };

        this._ws.onclose = () => {
            this._connected = false;
            this._notifyConnection();
            setTimeout(() => this.connect(), 2000);
        };

        this._ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            this._handleMessage(msg);
        };
    }

    _handleMessage(msg) {
        switch (msg.type) {
            case 'init':
            case 'state_update':
                this._state = msg.state;
                this._config = msg.state?.config || {};
                this._serverTimestamp = msg.state?.timestamp || (Date.now() / 1000);
                this._notify();
                break;
            case 'log':
                // Could emit a separate event for logs
                break;
        }
    }

    // Send message to server
    send(data) {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
            this._ws.send(JSON.stringify(data));
        }
    }

    // Action helpers
    toggleMotion() {
        const motionSensor = Object.entries(this.sensors).find(([id, s]) => s.type === 'motion');
        if (motionSensor) {
            this.send({
                type: 'sensor_event',
                sensor_id: motionSensor[0],
                state: !this.motionActive
            });
        }
    }

    toggleOverride() {
        const overrideSensor = Object.entries(this.sensors).find(([id, s]) => s.type === 'override');
        if (overrideSensor) {
            this.send({
                type: 'sensor_event',
                sensor_id: overrideSensor[0],
                state: !this.overrideActive
            });
        }
    }

    toggleLight() {
        const light = Object.entries(this.lights)[0];
        if (light) {
            this.send({
                type: 'light_event',
                light_id: light[0],
                action: light[1].is_on ? 'turn_off' : 'turn_on',
                is_manual: true
            });
        }
    }

    setLightBrightness(brightness) {
        const light = Object.entries(this.lights)[0];
        if (light) {
            const newBrightness = Math.max(0, Math.min(100, brightness));
            this.send({
                type: 'light_event',
                light_id: light[0],
                action: newBrightness === 0 ? 'turn_off' : 'turn_on',
                brightness: newBrightness,
                is_manual: true
            });
        }
    }

    setConfig(key, value) {
        this.send({ type: 'config_change', key, value });
    }

    reset() {
        this.send({ type: 'reset' });
    }
}

// Singleton instance
export const store = new StateStore();
