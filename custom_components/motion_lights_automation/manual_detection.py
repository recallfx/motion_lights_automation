"""Manual intervention detection strategies.

This module provides pluggable strategies for detecting when a user has
manually intervened with the lighting, allowing different detection logic
to be used based on preferences or requirements.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import logging

from homeassistant.core import Context

_LOGGER = logging.getLogger(__name__)


class ManualInterventionStrategy(ABC):
    """Abstract base class for manual intervention detection.
    
    Implement this interface to create custom detection strategies for
    determining when a user has manually controlled the lights vs. when
    the automation did it.
    
    Examples:
    - Brightness threshold detection (current default)
    - Time-window detection (changes within X seconds of automation)
    - User-specific detection (track which users trigger manual mode)
    - Device-specific detection (ignore changes from specific devices)
    """

    @abstractmethod
    def is_manual_intervention(
        self,
        entity_id: str,
        old_state: Any,
        new_state: Any,
        context: Context | None,
    ) -> tuple[bool, str | None]:
        """Determine if a state change represents manual intervention.
        
        Args:
            entity_id: Entity ID that changed
            old_state: Previous state
            new_state: New state
            context: Context of the state change
        
        Returns:
            Tuple of (is_manual, reason_string)
            - is_manual: True if this is manual intervention
            - reason_string: Human-readable explanation (if is_manual=True)
        """
        pass


class BrightnessThresholdStrategy(ManualInterventionStrategy):
    """Detect manual intervention based on brightness changes.
    
    This is the default strategy. It considers a change to be manual if:
    1. The light is turned on/off externally
    2. The brightness changes by more than a threshold percentage
    """

    def __init__(
        self,
        brightness_threshold_pct: int = 2,
        integration_contexts: set[str] | None = None,
    ):
        """Initialize the strategy.
        
        Args:
            brightness_threshold_pct: Minimum brightness change to consider manual
            integration_contexts: Set of context IDs originating from integration
        """
        self.brightness_threshold_pct = brightness_threshold_pct
        self.integration_contexts = integration_contexts or set()

    def is_manual_intervention(
        self,
        entity_id: str,
        old_state: Any,
        new_state: Any,
        context: Context | None,
    ) -> tuple[bool, str | None]:
        """Detect manual intervention based on state/brightness changes."""
        # Check if this change originated from our integration
        if self._is_integration_context(context):
            return False, None
        
        # Get states
        old_state_str = old_state.state if old_state else "unknown"
        new_state_str = new_state.state if new_state else "unknown"
        
        # Check for on/off state change
        if old_state_str != new_state_str:
            if new_state_str == "on" and old_state_str == "off":
                return True, f"light turned on manually: {entity_id}"
            elif new_state_str == "off" and old_state_str == "on":
                return True, f"light turned off manually: {entity_id}"
        
        # Check for significant brightness change
        if new_state_str == "on" and old_state_str == "on":
            old_brightness = self._get_brightness_pct(old_state)
            new_brightness = self._get_brightness_pct(new_state)
            brightness_diff = abs(new_brightness - old_brightness)
            
            if brightness_diff >= self.brightness_threshold_pct:
                return True, f"brightness changed manually: {entity_id} ({old_brightness}% → {new_brightness}%)"
        
        return False, None

    def _is_integration_context(self, context: Context | None) -> bool:
        """Check if context originated from integration."""
        if not context:
            return False
        return (
            context.id in self.integration_contexts
            or (context.parent_id and context.parent_id in self.integration_contexts)
        )

    def _get_brightness_pct(self, state: Any) -> int:
        """Get brightness as percentage from state."""
        if not state or state.state != "on":
            return 0
        brightness = state.attributes.get("brightness", 0) or 0
        return int(brightness * 100 / 255) if brightness else 0


class TimeWindowStrategy(ManualInterventionStrategy):
    """Detect manual intervention based on time windows.
    
    This strategy considers changes to be non-manual if they occur within
    a short time window after an automation action.
    """

    def __init__(
        self,
        window_seconds: float = 5.0,
        integration_contexts: set[str] | None = None,
    ):
        """Initialize the strategy.
        
        Args:
            window_seconds: Time window to ignore changes after automation
            integration_contexts: Set of context IDs from integration
        """
        self.window_seconds = window_seconds
        self.integration_contexts = integration_contexts or set()
        self._last_automation_time: float = 0

    def mark_automation_action(self) -> None:
        """Mark that an automation action just occurred."""
        import time
        self._last_automation_time = time.monotonic()

    def is_manual_intervention(
        self,
        entity_id: str,
        old_state: Any,
        new_state: Any,
        context: Context | None,
    ) -> tuple[bool, str | None]:
        """Detect manual intervention based on time windows."""
        # Check if context is from integration
        if context and (
            context.id in self.integration_contexts
            or (context.parent_id and context.parent_id in self.integration_contexts)
        ):
            return False, None
        
        # Check if within time window
        import time
        time_since_automation = time.monotonic() - self._last_automation_time
        if time_since_automation < self.window_seconds:
            _LOGGER.debug(
                "Change within time window (%.1fs), not considering manual",
                time_since_automation,
            )
            return False, None
        
        # Outside window - check for significant change
        old_state_str = old_state.state if old_state else "unknown"
        new_state_str = new_state.state if new_state else "unknown"
        
        if old_state_str != new_state_str:
            return True, f"light state changed outside automation window: {entity_id}"
        
        return False, None


class CombinedStrategy(ManualInterventionStrategy):
    """Combine multiple strategies with AND or OR logic.
    
    This allows creating complex detection logic by combining simpler strategies.
    """

    def __init__(
        self,
        strategies: list[ManualInterventionStrategy],
        logic: str = "OR",
    ):
        """Initialize combined strategy.
        
        Args:
            strategies: List of strategies to combine
            logic: "AND" or "OR" - how to combine results
        """
        self.strategies = strategies
        self.logic = logic.upper()
        if self.logic not in ("AND", "OR"):
            raise ValueError("logic must be 'AND' or 'OR'")

    def is_manual_intervention(
        self,
        entity_id: str,
        old_state: Any,
        new_state: Any,
        context: Context | None,
    ) -> tuple[bool, str | None]:
        """Detect manual intervention using combined strategies."""
        results = []
        reasons = []
        
        for strategy in self.strategies:
            is_manual, reason = strategy.is_manual_intervention(
                entity_id, old_state, new_state, context
            )
            results.append(is_manual)
            if reason:
                reasons.append(reason)
        
        if self.logic == "AND":
            is_manual = all(results)
        else:  # OR
            is_manual = any(results)
        
        reason = "; ".join(reasons) if is_manual and reasons else None
        return is_manual, reason


class ManualInterventionDetector:
    """Manages manual intervention detection with pluggable strategies.
    
    This class provides a clean interface for detecting manual intervention
    that can work with different detection strategies.
    
    To use a custom strategy:
    1. Create a class inheriting from ManualInterventionStrategy
    2. Implement is_manual_intervention() method
    3. Set it with set_strategy()
    
    Example custom strategies:
    - User-aware detection (different rules per user)
    - Room-aware detection (different rules per room)
    - Learning detection (adapt based on user behavior)
    - Priority-based detection (some lights always manual)
    """

    def __init__(self, strategy: ManualInterventionStrategy | None = None):
        """Initialize the detector.
        
        Args:
            strategy: Detection strategy to use (default: BrightnessThresholdStrategy)
        """
        self._strategy = strategy or BrightnessThresholdStrategy()
        self._last_manual_reason: str | None = None

    def set_strategy(self, strategy: ManualInterventionStrategy) -> None:
        """Set the detection strategy."""
        self._strategy = strategy
        _LOGGER.info("Updated manual intervention strategy to %s", type(strategy).__name__)

    def check_intervention(
        self,
        entity_id: str,
        old_state: Any,
        new_state: Any,
        context: Context | None,
    ) -> bool:
        """Check if a state change represents manual intervention.
        
        Returns:
            True if manual intervention detected
        """
        is_manual, reason = self._strategy.is_manual_intervention(
            entity_id, old_state, new_state, context
        )
        
        if is_manual:
            self._last_manual_reason = reason
            _LOGGER.info("Manual intervention detected: %s", reason)
        
        return is_manual

    def get_last_reason(self) -> str | None:
        """Get the reason for the last manual intervention detected."""
        return self._last_manual_reason

    def get_info(self) -> dict[str, Any]:
        """Get diagnostic information."""
        return {
            "strategy": type(self._strategy).__name__,
            "last_manual_reason": self._last_manual_reason,
        }
