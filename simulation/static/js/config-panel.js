import { LitElement, html, css } from 'https://cdn.jsdelivr.net/npm/lit@3/+esm';
import { store } from './state-store.js';

/**
 * Toggle switch component
 */
export class ToggleSwitch extends LitElement {
    static properties = {
        checked: { type: Boolean },
        disabled: { type: Boolean },
    };

    static styles = css`
        :host {
            display: inline-block;
        }
        .toggle {
            position: relative;
            width: 48px;
            height: 24px;
            cursor: pointer;
        }
        .toggle.disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        input {
            opacity: 0;
            width: 0;
            height: 0;
            position: absolute;
        }
        .toggle-track {
            position: absolute;
            inset: 0;
            background: var(--bg-component, #0f3460);
            border: 1px solid var(--border, #2a2a4a);
            border-radius: 12px;
            transition: 0.2s;
        }
        .toggle-thumb {
            position: absolute;
            top: 3px;
            left: 3px;
            width: 16px;
            height: 16px;
            background: var(--text-dim, #888);
            border-radius: 50%;
            transition: 0.2s;
        }
        input:checked + .toggle-track {
            background: var(--green-dim, #004d29);
            border-color: var(--green, #00ff88);
        }
        input:checked + .toggle-track .toggle-thumb {
            transform: translateX(24px);
            background: var(--green, #00ff88);
        }
    `;

    constructor() {
        super();
        this.checked = false;
        this.disabled = false;
    }

    render() {
        return html`
            <label class="toggle ${this.disabled ? 'disabled' : ''}">
                <input
                    type="checkbox"
                    .checked=${this.checked}
                    ?disabled=${this.disabled}
                    @change=${this._handleChange}
                >
                <div class="toggle-track">
                    <div class="toggle-thumb"></div>
                </div>
            </label>
        `;
    }

    _handleChange(e) {
        if (!this.disabled) {
            this.dispatchEvent(new CustomEvent('toggle-change', {
                detail: { checked: e.target.checked },
                bubbles: true,
                composed: true
            }));
        }
    }
}

customElements.define('toggle-switch', ToggleSwitch);

/**
 * Configuration panel with toggle switches
 */
export class ConfigPanel extends LitElement {
    static properties = {
        _motionActivation: { state: true },
        _houseActive: { state: true },
        _darkInside: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .panel {
            background: var(--bg-panel, #16213e);
            border: 1px solid var(--border, #2a2a4a);
            border-radius: 8px;
            padding: 16px;
        }
        .panel-title {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-dim, #888);
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border, #2a2a4a);
        }
        .control-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid var(--border, #2a2a4a);
        }
        .control-row:last-child {
            border-bottom: none;
        }
        .control-label {
            font-size: 12px;
        }
        .control-status {
            font-size: 10px;
            color: var(--text-dim, #888);
        }
    `;

    constructor() {
        super();
        this._motionActivation = true;
        this._houseActive = true;
        this._darkInside = true;
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
        this._motionActivation = store.config.motion_activation !== false;
        this._houseActive = store.config.is_house_active !== false;
        this._darkInside = store.config.is_dark_inside !== false;
    }

    render() {
        return html`
            <div class="panel">
                <div class="panel-title">Configuration</div>

                <div class="control-row">
                    <div>
                        <div class="control-label">Motion Activation</div>
                        <div class="control-status">Auto turn on lights</div>
                    </div>
                    <toggle-switch
                        ?checked=${this._motionActivation}
                        @toggle-change=${(e) => store.setConfig('motion_activation', e.detail.checked)}
                    ></toggle-switch>
                </div>

                <div class="control-row">
                    <div>
                        <div class="control-label">House Active</div>
                        <div class="control-status">Full brightness mode</div>
                    </div>
                    <toggle-switch
                        ?checked=${this._houseActive}
                        @toggle-change=${(e) => store.setConfig('is_house_active', e.detail.checked)}
                    ></toggle-switch>
                </div>

                <div class="control-row">
                    <div>
                        <div class="control-label">Dark Inside</div>
                        <div class="control-status">Ambient light sensor</div>
                    </div>
                    <toggle-switch
                        ?checked=${this._darkInside}
                        @toggle-change=${(e) => store.setConfig('is_dark_inside', e.detail.checked)}
                    ></toggle-switch>
                </div>
            </div>
        `;
    }
}

customElements.define('config-panel', ConfigPanel);

/**
 * Actions panel with reset button
 */
export class ActionsPanel extends LitElement {
    static styles = css`
        :host {
            display: block;
        }
        .panel {
            background: var(--bg-panel, #16213e);
            border: 1px solid var(--border, #2a2a4a);
            border-radius: 8px;
            padding: 16px;
        }
        .panel-title {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-dim, #888);
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border, #2a2a4a);
        }
        .action-btn {
            width: 100%;
            padding: 16px;
            background: var(--bg-component, #0f3460);
            border: 2px solid var(--border, #2a2a4a);
            border-radius: 6px;
            color: var(--text, #e8e8e8);
            font-family: inherit;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            cursor: pointer;
            transition: all 0.15s;
        }
        .action-btn:hover {
            border-color: var(--accent, #00d9ff);
            background: var(--accent-dim, #006680);
        }
        .action-btn:active {
            transform: scale(0.98);
        }
        .action-btn.danger {
            border-color: var(--red-dim, #4d151a);
        }
        .action-btn.danger:hover {
            border-color: var(--red, #ff4757);
            background: var(--red-dim, #4d151a);
            color: var(--red, #ff4757);
        }
    `;

    render() {
        return html`
            <div class="panel">
                <div class="panel-title">Actions</div>
                <button class="action-btn danger" @click=${() => store.reset()}>
                    Reset Simulation
                </button>
            </div>
        `;
    }
}

customElements.define('actions-panel', ActionsPanel);
