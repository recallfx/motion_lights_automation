import { LitElement, html, css, svg } from 'https://cdn.jsdelivr.net/npm/lit@3/+esm';
import { store } from './state-store.js';

/**
 * SVG Flow Diagram - shows the complete dependency flow using SVG for precise rendering
 *
 *                      [Override]
 *                          ↓
 * Motion → Activation → Coordinator → Light Output
 *                                          ↑
 *                          [Dark Inside] [House Active]
 */
export class FlowDiagram extends LitElement {
    static properties = {
        _motionActive: { state: true },
        _overrideActive: { state: true },
        _lightOn: { state: true },
        _lightBrightness: { state: true },
        _currentState: { state: true },
        _motionActivationEnabled: { state: true },
        _darkInside: { state: true },
        _houseActive: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .flow-container {
            width: 100%;
            overflow-x: auto;
        }
        svg {
            display: block;
            max-width: 100%;
            height: auto;
        }
        .node {
            cursor: pointer;
        }
        .node:hover rect {
            filter: brightness(1.2);
        }
        .node-rect {
            fill: #0f3460;
            stroke: #2a2a4a;
            stroke-width: 2;
            rx: 6;
            transition: all 0.2s;
        }
        .node-rect.active {
            stroke: #00ff88;
            filter: drop-shadow(0 0 8px rgba(0, 255, 136, 0.4));
        }
        .node-rect.warning {
            stroke: #ffcc00;
            filter: drop-shadow(0 0 8px rgba(255, 204, 0, 0.4));
        }
        .node-rect.error {
            stroke: #ff4757;
            filter: drop-shadow(0 0 8px rgba(255, 71, 87, 0.4));
        }
        .node-rect.disabled {
            opacity: 0.5;
            stroke: #2a2a4a;
        }
        .node-label {
            fill: #888;
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-family: inherit;
        }
        .node-value {
            fill: #e8e8e8;
            font-size: 14px;
            font-weight: 600;
            font-family: inherit;
        }
        .node-value.large {
            font-size: 16px;
        }
        .node-status {
            fill: #888;
            font-size: 10px;
            font-family: inherit;
        }
        .node-status.active {
            fill: #00ff88;
        }
        .arrow-line {
            stroke: #2a2a4a;
            stroke-width: 2;
            fill: none;
        }
        .arrow-line.active {
            stroke: #00ff88;
            filter: drop-shadow(0 0 4px rgba(0, 255, 136, 0.6));
        }
        .arrow-head {
            fill: #2a2a4a;
        }
        .arrow-head.active {
            fill: #00ff88;
        }
    `;

    constructor() {
        super();
        this._motionActive = false;
        this._overrideActive = false;
        this._lightOn = false;
        this._lightBrightness = 0;
        this._currentState = 'idle';
        this._motionActivationEnabled = true;
        this._darkInside = true;
        this._houseActive = true;
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
        this._motionActive = store.motionActive;
        this._overrideActive = store.overrideActive;
        this._lightOn = store.lightData.is_on;
        this._lightBrightness = store.lightData.brightness_pct;
        this._currentState = store.currentState;
        this._motionActivationEnabled = store.config.motion_activation !== false;
        this._darkInside = store.config.is_dark_inside !== false;
        this._houseActive = store.config.is_house_active !== false;
    }

    _getCoordinatorState() {
        const state = this._currentState;
        const isProcessing = ['motion-auto', 'motion-manual', 'auto', 'manual'].includes(state);
        return {
            active: isProcessing,
            warning: state === 'manual-off',
            error: state === 'overridden',
        };
    }

    get _motionSignalActive() {
        return this._motionActive && this._motionActivationEnabled;
    }

    _renderNode(x, y, w, h, label, value, status, { active, warning, error, disabled, onClick } = {}) {
        const rectClass = [
            'node-rect',
            active && !disabled ? 'active' : '',
            warning && !disabled ? 'warning' : '',
            error && !disabled ? 'error' : '',
            disabled ? 'disabled' : ''
        ].filter(Boolean).join(' ');

        const statusClass = active && !disabled ? 'node-status active' : 'node-status';

        return svg`
            <g class="node" @click=${onClick}>
                <rect class="${rectClass}" x="${x}" y="${y}" width="${w}" height="${h}"/>
                <text class="node-label" x="${x + w/2}" y="${y + 16}" text-anchor="middle">${label}</text>
                <text class="node-value ${h > 70 ? 'large' : ''}" x="${x + w/2}" y="${y + h/2 + 4}" text-anchor="middle">${value}</text>
                <text class="${statusClass}" x="${x + w/2}" y="${y + h - 10}" text-anchor="middle">${status}</text>
            </g>
        `;
    }

    _renderArrow(x1, y1, x2, y2, active, direction = 'right') {
        const lineClass = active ? 'arrow-line active' : 'arrow-line';
        const headClass = active ? 'arrow-head active' : 'arrow-head';

        // Calculate arrow head points based on direction
        let headPoints;
        const size = 6;

        if (direction === 'right') {
            headPoints = `${x2},${y2} ${x2-size},${y2-size} ${x2-size},${y2+size}`;
        } else if (direction === 'down') {
            headPoints = `${x2},${y2} ${x2-size},${y2-size} ${x2+size},${y2-size}`;
        } else if (direction === 'up') {
            headPoints = `${x2},${y2} ${x2-size},${y2+size} ${x2+size},${y2+size}`;
        }

        return svg`
            <line class="${lineClass}" x1="${x1}" y1="${y1}" x2="${x2 - (direction === 'right' ? size : 0)}" y2="${y2 - (direction === 'down' ? size : direction === 'up' ? -size : 0)}"/>
            <polygon class="${headClass}" points="${headPoints}"/>
        `;
    }

    render() {
        const coordState = this._getCoordinatorState();

        // Layout constants
        const nodeW = 120;      // Standard node width
        const nodeH = 70;       // Standard node height
        const smallW = 100;     // Small node width
        const smallH = 60;      // Small node height
        const arrowLen = 40;    // Arrow length

        // Calculate positions (left to right flow)
        // Row 1 (main flow): Motion -> Activation -> Coordinator -> Light
        const motionX = 20;
        const motionY = 80;

        const activationX = motionX + nodeW + arrowLen;
        const activationY = motionY + (nodeH - smallH) / 2;

        const coordX = activationX + smallW + arrowLen;
        const coordY = motionY;

        const lightX = coordX + nodeW + arrowLen;
        const lightY = motionY;

        // Override (above coordinator)
        const overrideX = coordX + (nodeW - smallW) / 2;
        const overrideY = 5;

        // Dark Inside and House Active (below light, centered under light)
        const inputsY = lightY + nodeH + 35;
        const inputsTotalW = smallW * 2 + 10;
        const darkX = lightX + (nodeW - inputsTotalW) / 2;
        const houseX = darkX + smallW + 10;

        // SVG dimensions - ensure all elements fit
        const svgWidth = Math.max(lightX + nodeW + 20, houseX + smallW + 20);
        const svgHeight = inputsY + smallH + 20;

        return html`
            <div class="flow-container">
                <svg viewBox="0 0 ${svgWidth} ${svgHeight}" preserveAspectRatio="xMidYMid meet">
                    <!-- Arrow: Motion -> Activation -->
                    ${this._renderArrow(
                        motionX + nodeW, motionY + nodeH/2,
                        activationX, activationY + smallH/2,
                        this._motionActive, 'right'
                    )}

                    <!-- Arrow: Activation -> Coordinator -->
                    ${this._renderArrow(
                        activationX + smallW, activationY + smallH/2,
                        coordX, coordY + nodeH/2,
                        this._motionSignalActive, 'right'
                    )}

                    <!-- Arrow: Coordinator -> Light -->
                    ${this._renderArrow(
                        coordX + nodeW, coordY + nodeH/2,
                        lightX, lightY + nodeH/2,
                        this._lightOn, 'right'
                    )}

                    <!-- Arrow: Override -> Coordinator -->
                    ${this._renderArrow(
                        overrideX + smallW/2, overrideY + smallH,
                        coordX + nodeW/2, coordY,
                        this._overrideActive, 'down'
                    )}

                    <!-- Arrow: Inputs -> Light (from center of inputs) -->
                    ${this._renderArrow(
                        lightX + nodeW/2, inputsY,
                        lightX + nodeW/2, lightY + nodeH,
                        this._lightOn, 'up'
                    )}

                    <!-- Node: Motion Sensor -->
                    ${this._renderNode(motionX, motionY, nodeW, nodeH,
                        'Motion Sensor', '👁️',
                        this._motionActive ? 'Detected' : 'Clear',
                        { active: this._motionActive, onClick: () => store.toggleMotion() }
                    )}

                    <!-- Node: Motion Activation -->
                    ${this._renderNode(activationX, activationY, smallW, smallH,
                        'Activation', this._motionActivationEnabled ? '✓' : '✗',
                        this._motionActivationEnabled ? 'Enabled' : 'Disabled',
                        {
                            active: this._motionSignalActive,
                            disabled: !this._motionActivationEnabled,
                            onClick: () => store.setConfig('motion_activation', !this._motionActivationEnabled)
                        }
                    )}

                    <!-- Node: Override -->
                    ${this._renderNode(overrideX, overrideY, smallW, smallH,
                        'Override', '🔒',
                        this._overrideActive ? 'Active' : 'Inactive',
                        { active: this._overrideActive, error: this._overrideActive, onClick: () => store.toggleOverride() }
                    )}

                    <!-- Node: Coordinator -->
                    ${this._renderNode(coordX, coordY, nodeW, nodeH,
                        'Coordinator', this._currentState.toUpperCase().replace('-', ' '),
                        this._overrideActive ? 'Blocked' : 'Processing',
                        { active: coordState.active, warning: coordState.warning, error: coordState.error }
                    )}

                    <!-- Node: Light Output -->
                    ${this._renderNode(lightX, lightY, nodeW, nodeH,
                        'Light Output', `${this._lightBrightness}%`,
                        this._lightOn ? 'On' : 'Off',
                        { active: this._lightOn, onClick: () => store.toggleLight() }
                    )}

                    <!-- Node: Dark Inside -->
                    ${this._renderNode(darkX, inputsY, smallW, smallH,
                        'Dark Inside', this._darkInside ? '🌙' : '☀️',
                        this._darkInside ? 'Dark' : 'Bright',
                        { active: this._darkInside, onClick: () => store.setConfig('is_dark_inside', !this._darkInside) }
                    )}

                    <!-- Node: House Active -->
                    ${this._renderNode(houseX, inputsY, smallW, smallH,
                        'House Active', this._houseActive ? '🏠' : '😴',
                        this._houseActive ? '80%' : '10%',
                        { active: this._houseActive, onClick: () => store.setConfig('is_house_active', !this._houseActive) }
                    )}
                </svg>
            </div>
        `;
    }
}

customElements.define('flow-diagram', FlowDiagram);
