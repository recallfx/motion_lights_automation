import { LitElement, html, css } from 'https://cdn.jsdelivr.net/npm/lit@3/+esm';
import { store } from './state-store.js';

/**
 * Single timer display box
 */
export class TimerBox extends LitElement {
    static properties = {
        label: { type: String },
        timer: { type: Object },
        serverTimestamp: { type: Number },
        _remaining: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .timer-box {
            background: var(--bg-component, #0f3460);
            border: 1px solid var(--border, #2a2a4a);
            border-radius: 6px;
            padding: 16px;
        }
        .timer-box.active {
            border-color: var(--yellow, #ffcc00);
        }
        .timer-label {
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-dim, #888);
            margin-bottom: 8px;
        }
        .timer-value {
            font-size: 28px;
            font-weight: 700;
            font-family: 'SF Mono', monospace;
        }
        .timer-box.active .timer-value {
            color: var(--yellow, #ffcc00);
        }
        .timer-bar {
            margin-top: 8px;
            height: 4px;
            background: var(--border, #2a2a4a);
            border-radius: 2px;
            overflow: hidden;
        }
        .timer-bar-fill {
            height: 100%;
            background: var(--yellow, #ffcc00);
            transition: width 0.5s linear;
        }
    `;

    constructor() {
        super();
        this.label = '';
        this.timer = null;
        this.serverTimestamp = null;
        this._remaining = 0;
        this._intervalId = null;
    }

    connectedCallback() {
        super.connectedCallback();
        // Update every 500ms for smooth countdown
        this._intervalId = setInterval(() => this._updateRemaining(), 500);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._intervalId) {
            clearInterval(this._intervalId);
            this._intervalId = null;
        }
    }

    updated(changedProperties) {
        if (changedProperties.has('timer') || changedProperties.has('serverTimestamp')) {
            this._updateRemaining();
        }
    }

    _updateRemaining() {
        if (!this.timer?.active) {
            this._remaining = 0;
            return;
        }

        let remaining = this.timer.remaining || 0;
        if (this.serverTimestamp && this.timer.remaining !== undefined) {
            const elapsed = (Date.now() / 1000) - this.serverTimestamp;
            remaining = Math.max(0, this.timer.remaining - elapsed);
        }
        this._remaining = remaining;
    }

    _formatTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    render() {
        const active = this.timer?.active && this._remaining > 0;
        const duration = this.timer?.duration || 1;
        const percent = active ? (this._remaining / duration) * 100 : 0;

        return html`
            <div class="timer-box ${active ? 'active' : ''}">
                <div class="timer-label">${this.label}</div>
                <div class="timer-value">${active ? this._formatTime(this._remaining) : '--:--'}</div>
                <div class="timer-bar">
                    <div class="timer-bar-fill" style="width: ${percent}%"></div>
                </div>
            </div>
        `;
    }
}

customElements.define('timer-box', TimerBox);

/**
 * Timers section - displays all active timers
 */
export class TimersSection extends LitElement {
    static properties = {
        _timers: { state: true },
        _serverTimestamp: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .timers-section {
            margin-top: 24px;
            padding-top: 24px;
            border-top: 1px solid var(--border, #2a2a4a);
        }
        .section-title {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-dim, #888);
            margin-bottom: 16px;
        }
        .timers-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
        }
    `;

    constructor() {
        super();
        this._timers = {};
        this._serverTimestamp = null;
        this._unsubscribe = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = store.subscribe(() => this._updateFromStore());
        this._updateFromStore();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._unsubscribe) this._unsubscribe();
    }

    _updateFromStore() {
        this._timers = store.timers;
        this._serverTimestamp = store.serverTimestamp;
    }

    render() {
        return html`
            <div class="timers-section">
                <div class="section-title">Active Timers</div>
                <div class="timers-grid">
                    <timer-box
                        label="Motion Timer"
                        .timer=${this._timers.motion}
                        .serverTimestamp=${this._serverTimestamp}
                    ></timer-box>
                    <timer-box
                        label="Extended Timer"
                        .timer=${this._timers.extended}
                        .serverTimestamp=${this._serverTimestamp}
                    ></timer-box>
                </div>
            </div>
        `;
    }
}

customElements.define('timers-section', TimersSection);
