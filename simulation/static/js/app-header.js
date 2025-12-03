import { LitElement, html, css } from 'https://cdn.jsdelivr.net/npm/lit@3/+esm';
import { store } from './state-store.js';

/**
 * Connection indicator in header
 */
export class ConnectionStatus extends LitElement {
    static properties = {
        _connected: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .connection {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 11px;
        }
        .connection-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--red, #ff4757);
        }
        .connection-dot.connected {
            background: var(--green, #00ff88);
            box-shadow: 0 0 8px var(--green, #00ff88);
        }
    `;

    constructor() {
        super();
        this._connected = false;
        this._unsubscribe = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = store.subscribeConnection((connected) => {
            this._connected = connected;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._unsubscribe) this._unsubscribe();
    }

    render() {
        return html`
            <div class="connection">
                <div class="connection-dot ${this._connected ? 'connected' : ''}"></div>
                <span>${this._connected ? 'Connected' : 'Disconnected'}</span>
            </div>
        `;
    }
}

customElements.define('connection-status', ConnectionStatus);

/**
 * App header with reset button
 */
export class AppHeader extends LitElement {
    static styles = css`
        :host {
            display: block;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border, #2a2a4a);
        }
        h1 {
            font-size: 14px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: var(--text-dim, #888);
            margin: 0;
        }
        .header-right {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .reset-btn {
            padding: 6px 12px;
            background: transparent;
            border: 1px solid var(--border, #2a2a4a);
            border-radius: 4px;
            color: var(--text-dim, #888);
            font-family: inherit;
            font-size: 10px;
            font-weight: 500;
            letter-spacing: 1px;
            text-transform: uppercase;
            cursor: pointer;
            transition: all 0.2s;
        }
        .reset-btn:hover {
            border-color: var(--red, #ff4757);
            color: var(--red, #ff4757);
        }
    `;

    render() {
        return html`
            <div class="header">
                <h1>Motion Lights Automation</h1>
                <div class="header-right">
                    <button class="reset-btn" @click=${() => store.reset()}>Reset</button>
                    <connection-status></connection-status>
                </div>
            </div>
        `;
    }
}

customElements.define('app-header', AppHeader);
