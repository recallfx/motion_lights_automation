import { LitElement, html, css } from 'https://cdn.jsdelivr.net/npm/lit@3/+esm';
import { store } from './state-store.js';

/**
 * State machine display - shows current state and available states
 */
export class StateMachine extends LitElement {
    static properties = {
        _currentState: { state: true },
        _timeInState: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .state-section {
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
        .state-display {
            display: flex;
            align-items: center;
            gap: 24px;
        }
        .current-state {
            background: var(--bg-component, #0f3460);
            border: 2px solid var(--accent, #00d9ff);
            border-radius: 6px;
            padding: 16px 32px;
            text-align: center;
        }
        .state-name {
            font-size: 24px;
            font-weight: 700;
            color: var(--accent, #00d9ff);
            text-transform: uppercase;
        }
        .state-time {
            font-size: 11px;
            color: var(--text-dim, #888);
            margin-top: 4px;
        }
        .state-transitions {
            flex: 1;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .state-chip {
            background: var(--bg-component, #0f3460);
            border: 1px solid var(--border, #2a2a4a);
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 10px;
            color: var(--text-dim, #888);
            text-transform: uppercase;
        }
        .state-chip.available {
            border-color: var(--accent-dim, #006680);
            color: var(--accent, #00d9ff);
        }
    `;

    static STATES = [
        { id: 'idle', label: 'Idle' },
        { id: 'motion-auto', label: 'Motion Auto' },
        { id: 'auto', label: 'Auto' },
        { id: 'manual', label: 'Manual' },
        { id: 'motion-manual', label: 'Motion Manual' },
        { id: 'manual-off', label: 'Manual Off' },
        { id: 'overridden', label: 'Overridden' },
    ];

    constructor() {
        super();
        this._currentState = 'idle';
        this._timeInState = 0;
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
        this._currentState = store.currentState;
        this._timeInState = store.timeInState;
    }

    _formatDuration(seconds) {
        if (seconds < 60) return seconds + 's';
        if (seconds < 3600) return Math.floor(seconds / 60) + 'm ' + (seconds % 60) + 's';
        return Math.floor(seconds / 3600) + 'h ' + Math.floor((seconds % 3600) / 60) + 'm';
    }

    render() {
        return html`
            <div class="state-section">
                <div class="section-title">State Machine</div>
                <div class="state-display">
                    <div class="current-state">
                        <div class="state-name">${this._currentState.toUpperCase().replace('-', ' ')}</div>
                        <div class="state-time">${this._formatDuration(this._timeInState)} in state</div>
                    </div>
                    <div class="state-transitions">
                        ${StateMachine.STATES.map(s => html`
                            <div class="state-chip ${s.id === this._currentState ? 'available' : ''}">${s.label}</div>
                        `)}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('state-machine', StateMachine);
