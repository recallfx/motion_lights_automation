/**
 * Motion Lights Automation - Simulation Dashboard
 * Main entry point - imports all components and initializes the app
 */

import { store } from './state-store.js';

// Import all components
import './app-header.js';
import './flow-component.js';
import './state-machine.js';
import './state-flow.js';
import './timer-display.js';
import './event-log.js';
import './config-panel.js';

// Connect to WebSocket when page loads
store.connect();
