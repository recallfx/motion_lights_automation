import { LitElement, html, css, svg } from 'https://cdn.jsdelivr.net/npm/lit@3/+esm';
import { store } from './state-store.js';

/**
 * State Flow Diagram - Clean SVG visualization of state machine transitions
 *
 * Layout (organized by flow):
 *
 *                    [DISABLED]
 *                         ↑
 *   [STANDBY] ←── [MOTION-DETECTED] ←──→ [AUTO-TIMEOUT]
 *       ↑              ↓                      ↓
 *       │         [MOTION-ADJUSTED] ←→ [MANUAL-TIMEOUT]
 *       │                    ↘          ↙
 *       └──────────────── [USER-BLOCKED]
 */
export class StateFlow extends LitElement {
    static properties = {
        _currentState: { state: true },
        _previousState: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .flow-container {
            width: 100%;
            overflow-x: auto;
            margin-top: 16px;
        }
        svg {
            display: block;
            max-width: 100%;
            height: auto;
        }
        .state-rect {
            fill: #0f3460;
            stroke: #2a2a4a;
            stroke-width: 2;
            transition: all 0.3s ease;
        }
        .state-rect.current {
            fill: #1a4a80;
            stroke: #00d9ff;
            stroke-width: 3;
            filter: drop-shadow(0 0 12px rgba(0, 217, 255, 0.5));
        }
        .state-rect.previous {
            stroke: #006680;
            stroke-dasharray: 4 2;
        }
        .state-label {
            fill: #888;
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-family: inherit;
            pointer-events: none;
        }
        .state-label.current {
            fill: #00d9ff;
        }
        .transition-path {
            fill: none;
            stroke-width: 1.5;
            transition: all 0.3s ease;
        }
        .transition-path.active {
            stroke: #00ff88 !important;
            stroke-width: 2.5;
            filter: drop-shadow(0 0 4px rgba(0, 255, 136, 0.6));
        }
        .transition-path.motion { stroke: #ffcc00; }
        .transition-path.manual { stroke: #ff6b9d; }
        .transition-path.timer { stroke: #00d9ff; }
        .transition-path.override { stroke: #ff4757; }

        .legend {
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            margin-top: 12px;
            padding: 12px;
            background: rgba(15, 52, 96, 0.3);
            border-radius: 6px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 10px;
            color: #888;
        }
        .legend-line {
            width: 20px;
            height: 2px;
        }
        .legend-line.motion { background: #ffcc00; }
        .legend-line.manual { background: #ff6b9d; }
        .legend-line.timer { background: #00d9ff; }
        .legend-line.override { background: #ff4757; }
    `;

    // State positions - organized in a cleaner grid
    static STATE_POSITIONS = {
        'disabled': { x: 220, y: 35, w: 80, h: 32 },
        'standby': { x: 60, y: 110, w: 70, h: 32 },
        'motion-detected': { x: 220, y: 110, w: 115, h: 32 },
        'auto-timeout': { x: 380, y: 110, w: 95, h: 32 },
        'motion-adjusted': { x: 220, y: 195, w: 115, h: 32 },
        'manual-timeout': { x: 380, y: 195, w: 110, h: 32 },
        'manual-off': { x: 220, y: 280, w: 85, h: 32 },
    };

    // Curated transitions with explicit path types for clean routing
    static TRANSITIONS = [
        // === Main horizontal motion flow (top row) ===
        { from: 'standby', to: 'motion-detected', type: 'motion', offsetY: 0 },
        { from: 'motion-detected', to: 'auto-timeout', type: 'motion', offsetY: -5 },
        { from: 'auto-timeout', to: 'motion-detected', type: 'motion', offsetY: 5 },

        // === Manual intervention (vertical down) ===
        { from: 'motion-detected', to: 'motion-adjusted', type: 'manual', offsetX: 0 },
        { from: 'auto-timeout', to: 'manual-timeout', type: 'manual', offsetX: 0 },

        // === Motion in manual states (horizontal) ===
        { from: 'manual-timeout', to: 'motion-adjusted', type: 'motion', offsetY: -5 },
        { from: 'motion-adjusted', to: 'manual-timeout', type: 'motion', offsetY: 5 },

        // === Manual OFF (converging down) ===
        { from: 'motion-adjusted', to: 'manual-off', type: 'manual', offsetX: -15 },
        { from: 'manual-timeout', to: 'manual-off', type: 'manual', curve: 'down-left' },

        // === Lights off transitions to manual-off ===
        { from: 'motion-detected', to: 'manual-off', type: 'manual', curve: 'down-around-left' },
        { from: 'auto-timeout', to: 'manual-off', type: 'manual', curve: 'down-around-right' },

        // === Timer returns to standby (curved, avoiding other arrows) ===
        { from: 'auto-timeout', to: 'standby', type: 'timer', curve: 'over-top' },
        { from: 'manual-timeout', to: 'standby', type: 'timer', curve: 'big-left' },
        { from: 'manual-off', to: 'standby', type: 'timer', curve: 'bottom-left' },

        // === Manual ON from manual-off ===
        { from: 'manual-off', to: 'manual-timeout', type: 'manual', curve: 'up-right' },

        // === Override (to disabled) ===
        { from: 'motion-detected', to: 'disabled', type: 'override', offsetX: 0 },

        // === Override OFF ===
        { from: 'disabled', to: 'standby', type: 'override', curve: 'down-left' },
        { from: 'disabled', to: 'manual-timeout', type: 'override', curve: 'down-far-right' },

        // === Standby to manual (direct manual light on) ===
        { from: 'standby', to: 'manual-timeout', type: 'manual', curve: 'diagonal-down' },
    ];

    constructor() {
        super();
        this._currentState = 'idle';
        this._previousState = null;
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
        const prev = this._currentState;
        this._currentState = store.currentState;
        if (store.state.previous_state) {
            this._previousState = store.state.previous_state;
        } else if (prev !== this._currentState) {
            this._previousState = prev;
        }
    }

    _getStateLabel(stateId) {
        const labels = {
            'standby': 'STANDBY',
            'motion-detected': 'MOTION DETECTED',
            'auto-timeout': 'AUTO TIMEOUT',
            'motion-adjusted': 'MOTION ADJUSTED',
            'manual-timeout': 'MANUAL TIMEOUT',
            'manual-off': 'MANUAL OFF',
            'disabled': 'DISABLED',
        };
        return labels[stateId] || stateId.toUpperCase();
    }

    _renderState(stateId) {
        const s = StateFlow.STATE_POSITIONS[stateId];
        const isCurrent = stateId === this._currentState;
        const isPrevious = stateId === this._previousState;
        const label = this._getStateLabel(stateId);

        return svg`
            <g class="state-node">
                <rect
                    class="state-rect ${isCurrent ? 'current' : ''} ${isPrevious ? 'previous' : ''}"
                    x="${s.x - s.w / 2}" y="${s.y - s.h / 2}"
                    width="${s.w}" height="${s.h}" rx="6"
                />
                <text
                    class="state-label ${isCurrent ? 'current' : ''}"
                    x="${s.x}" y="${s.y + 4}" text-anchor="middle"
                >${label}</text>
            </g>
        `;
    }

    _buildPath(transition) {
        const from = StateFlow.STATE_POSITIONS[transition.from];
        const to = StateFlow.STATE_POSITIONS[transition.to];
        const offsetX = transition.offsetX || 0;
        const offsetY = transition.offsetY || 0;

        // Calculate direction
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const isHorizontal = Math.abs(dx) > Math.abs(dy);

        let x1, y1, x2, y2;

        // Determine edge exit/entry points
        if (isHorizontal) {
            x1 = dx > 0 ? from.x + from.w / 2 : from.x - from.w / 2;
            x2 = dx > 0 ? to.x - to.w / 2 : to.x + to.w / 2;
            y1 = from.y + offsetY;
            y2 = to.y + offsetY;
        } else {
            y1 = dy > 0 ? from.y + from.h / 2 : from.y - from.h / 2;
            y2 = dy > 0 ? to.y - to.h / 2 : to.y + to.h / 2;
            x1 = from.x + offsetX;
            x2 = to.x + offsetX;
        }

        // Handle special curve types
        if (transition.curve) {
            return this._buildCurvedPath(transition.curve, from, to);
        }

        // Straight line with small gap for arrow
        return `M ${x1} ${y1} L ${x2} ${y2}`;
    }

    _buildCurvedPath(curveType, from, to) {
        switch (curveType) {
            case 'over-top': {
                // Timer: auto -> idle, curve over the top
                const x1 = from.x - from.w / 2;
                const y1 = from.y - 8;
                const x2 = to.x + to.w / 2;
                const y2 = to.y - 8;
                return `M ${x1} ${y1} C ${x1 - 20} ${y1 - 40}, ${x2 + 20} ${y2 - 40}, ${x2} ${y2}`;
            }

            case 'big-left': {
                // Timer: manual -> idle, big curve around the left side
                const x1 = from.x - from.w / 2;
                const y1 = from.y;
                const x2 = to.x;
                const y2 = to.y + to.h / 2;
                return `M ${x1} ${y1} C ${-10} ${y1}, ${-10} ${y2 + 40}, ${x2} ${y2}`;
            }

            case 'bottom-left': {
                // Timer: manual-off -> idle
                const x1 = from.x - from.w / 2;
                const y1 = from.y;
                const x2 = to.x;
                const y2 = to.y + to.h / 2;
                return `M ${x1} ${y1} C ${x1 - 50} ${y1 + 10}, ${x2 - 30} ${y2 + 40}, ${x2} ${y2}`;
            }

            case 'up-right': {
                // Manual: manual-off -> manual
                const x1 = from.x + from.w / 2;
                const y1 = from.y - 5;
                const x2 = to.x;
                const y2 = to.y + to.h / 2;
                return `M ${x1} ${y1} Q ${x1 + 50} ${(y1 + y2) / 2} ${x2} ${y2}`;
            }

            case 'down-left': {
                // Manual: manual -> manual-off or override -> idle
                const x1 = from.x - from.w / 2 + 10;
                const y1 = from.y + from.h / 2;
                const x2 = to.x + to.w / 2 - 10;
                const y2 = to.y - to.h / 2;
                return `M ${x1} ${y1} Q ${(x1 + x2) / 2 - 20} ${(y1 + y2) / 2} ${x2} ${y2}`;
            }

            case 'down-far-right': {
                // Override: overridden -> manual
                const x1 = from.x + from.w / 2;
                const y1 = from.y + 5;
                const x2 = to.x;
                const y2 = to.y - to.h / 2;
                return `M ${x1} ${y1} C ${x1 + 60} ${y1 + 30}, ${x2 + 30} ${y2 - 40}, ${x2} ${y2}`;
            }

            case 'diagonal-down': {
                // Manual: idle -> manual
                const x1 = from.x + from.w / 2;
                const y1 = from.y + 8;
                const x2 = to.x - to.w / 2;
                const y2 = to.y - 8;
                return `M ${x1} ${y1} C ${x1 + 40} ${y1 + 30}, ${x2 - 40} ${y2 - 30}, ${x2} ${y2}`;
            }

            case 'down-around-left': {
                // Manual off: motion-auto -> manual-off (left side)
                const x1 = from.x - from.w / 2 + 5;
                const y1 = from.y + from.h / 2;
                const x2 = to.x - to.w / 2 + 5;
                const y2 = to.y - to.h / 2;
                return `M ${x1} ${y1} C ${x1 - 35} ${y1 + 40}, ${x2 - 35} ${y2 - 40}, ${x2} ${y2}`;
            }

            case 'down-around-right': {
                // Manual off: auto -> manual-off (right side)
                const x1 = from.x;
                const y1 = from.y + from.h / 2;
                const x2 = to.x + to.w / 2 - 5;
                const y2 = to.y - to.h / 2;
                return `M ${x1} ${y1} C ${x1 + 20} ${y1 + 60}, ${x2 + 35} ${y2 - 40}, ${x2} ${y2}`;
            }

            default:
                return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
        }
    }

    _renderTransition(transition) {
        const isActive = this._previousState === transition.from &&
            this._currentState === transition.to;

        const path = this._buildPath(transition);

        return svg`
            <path
                class="transition-path ${transition.type} ${isActive ? 'active' : ''}"
                d="${path}"
                marker-end="url(#arrow-${transition.type}${isActive ? '-active' : ''})"
            />
        `;
    }

    _renderMarkers() {
        const types = [
            { name: 'motion', color: '#ffcc00' },
            { name: 'manual', color: '#ff6b9d' },
            { name: 'timer', color: '#00d9ff' },
            { name: 'override', color: '#ff4757' },
        ];

        return svg`
            <defs>
                ${types.map(t => svg`
                    <marker id="arrow-${t.name}" markerWidth="8" markerHeight="8"
                            refX="7" refY="4" orient="auto">
                        <path d="M 0 0 L 8 4 L 0 8 L 2 4 Z" fill="${t.color}" />
                    </marker>
                    <marker id="arrow-${t.name}-active" markerWidth="10" markerHeight="10"
                            refX="8" refY="5" orient="auto">
                        <path d="M 0 0 L 10 5 L 0 10 L 2.5 5 Z" fill="#00ff88" />
                    </marker>
                `)}
            </defs>
        `;
    }

    render() {
        const states = Object.keys(StateFlow.STATE_POSITIONS);

        return html`
            <div class="flow-container">
                <svg viewBox="0 0 440 320" preserveAspectRatio="xMidYMid meet">
                    ${this._renderMarkers()}

                    <!-- Transitions (behind states) -->
                    <g class="transitions">
                        ${StateFlow.TRANSITIONS.map(t => this._renderTransition(t))}
                    </g>

                    <!-- States (on top) -->
                    <g class="states">
                        ${states.map(s => this._renderState(s))}
                    </g>
                </svg>
            </div>

            <div class="legend">
                <div class="legend-item">
                    <div class="legend-line motion"></div>
                    <span>Motion</span>
                </div>
                <div class="legend-item">
                    <div class="legend-line manual"></div>
                    <span>Manual</span>
                </div>
                <div class="legend-item">
                    <div class="legend-line timer"></div>
                    <span>Timer</span>
                </div>
                <div class="legend-item">
                    <div class="legend-line override"></div>
                    <span>Override</span>
                </div>
            </div>
        `;
    }
}

customElements.define('state-flow', StateFlow);
