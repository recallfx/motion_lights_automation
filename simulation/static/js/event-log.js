import { LitElement, html, css } from 'https://cdn.jsdelivr.net/npm/lit@3/+esm';
import { store } from './state-store.js';

/**
 * Event log display
 */
export class EventLog extends LitElement {
    static properties = {
        _entries: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .log-section {
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
        .log-container {
            max-height: 200px;
            overflow-y: auto;
            background: var(--bg-component, #0f3460);
            border-radius: 6px;
            padding: 12px;
        }
        .log-entry {
            padding: 6px 0;
            border-bottom: 1px solid var(--border, #2a2a4a);
            font-size: 11px;
        }
        .log-entry:last-child {
            border-bottom: none;
        }
        .log-time {
            color: var(--text-dim, #888);
            margin-right: 8px;
        }
        .log-entry.transition {
            color: var(--accent, #00d9ff);
        }
        .log-entry.sensor {
            color: var(--green, #00ff88);
        }
        .log-entry.light {
            color: var(--yellow, #ffcc00);
        }
        .log-entry.timer {
            color: #c084fc;
        }
        .log-entry.info {
            color: var(--text, #e8e8e8);
        }
        .log-entry.error {
            color: var(--red, #ff4757);
        }
        .empty-message {
            color: var(--text-dim, #888);
            font-style: italic;
        }
    `;

    constructor() {
        super();
        this._entries = [];
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
        this._entries = store.eventLog.slice(-15).reverse();
    }

    _formatTime(timestamp) {
        return new Date(timestamp).toLocaleTimeString('en-US', { hour12: false });
    }

    render() {
        return html`
            <div class="log-section">
                <div class="section-title">Event Log</div>
                <div class="log-container">
                    ${this._entries.length === 0
                        ? html`<div class="empty-message">Waiting for events...</div>`
                        : this._entries.map(entry => html`
                            <div class="log-entry ${entry.type || 'info'}">
                                <span class="log-time">${this._formatTime(entry.timestamp)}</span>${entry.message}
                            </div>
                        `)
                    }
                </div>
            </div>
        `;
    }
}

customElements.define('event-log', EventLog);
