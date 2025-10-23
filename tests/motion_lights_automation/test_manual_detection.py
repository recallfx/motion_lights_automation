"""Comprehensive tests for manual_detection.py."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from homeassistant.core import Context




from homeassistant.components.motion_lights_automation.manual_detection import (
    ManualInterventionDetector,
    BrightnessThresholdStrategy,
    TimeWindowStrategy,
    CombinedStrategy,
    ManualInterventionStrategy,
)


class TestBrightnessThresholdStrategy:
    """Test BrightnessThresholdStrategy class."""

    def test_light_turned_on_manually(self):
        """Test detection when light turned on."""
        strategy = BrightnessThresholdStrategy()
        
        old_state = MagicMock()
        old_state.state = "off"
        old_state.attributes = {}
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 128}
        
        is_manual, reason = strategy.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        assert is_manual is True
        assert "turned on manually" in reason

    def test_light_turned_off_manually(self):
        """Test detection when light turned off."""
        strategy = BrightnessThresholdStrategy()
        
        old_state = MagicMock()
        old_state.state = "on"
        old_state.attributes = {"brightness": 128}
        
        new_state = MagicMock()
        new_state.state = "off"
        new_state.attributes = {}
        
        is_manual, reason = strategy.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        assert is_manual is True
        assert "turned off manually" in reason

    def test_brightness_change_above_threshold(self):
        """Test detection when brightness changes significantly."""
        strategy = BrightnessThresholdStrategy(brightness_threshold_pct=10)
        
        old_state = MagicMock()
        old_state.state = "on"
        old_state.attributes = {"brightness": 51}  # 20%
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 153}  # 60%
        
        is_manual, reason = strategy.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        assert is_manual is True
        assert "brightness changed manually" in reason

    def test_brightness_change_below_threshold(self):
        """Test no detection when brightness change is small."""
        strategy = BrightnessThresholdStrategy(brightness_threshold_pct=10)
        
        old_state = MagicMock()
        old_state.state = "on"
        old_state.attributes = {"brightness": 128}  # 50%
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 133}  # 52%
        
        is_manual, reason = strategy.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        assert is_manual is False
        assert reason is None

    def test_integration_context_ignored(self):
        """Test that integration contexts are ignored."""
        context_id = "test_context_123"
        strategy = BrightnessThresholdStrategy(
            integration_contexts={context_id}
        )
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 128}
        
        context = Context()
        context.id = context_id
        
        is_manual, reason = strategy.is_manual_intervention(
            "light.test", old_state, new_state, context
        )
        
        assert is_manual is False
        assert reason is None


class TestTimeWindowStrategy:
    """Test TimeWindowStrategy class."""

    def test_change_within_window_ignored(self):
        """Test that changes within time window are ignored."""
        strategy = TimeWindowStrategy(window_seconds=5.0)
        strategy.mark_automation_action()
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        
        is_manual, reason = strategy.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        assert is_manual is False
        assert reason is None

    def test_change_outside_window_detected(self):
        """Test that changes outside time window are detected."""
        import time
        
        strategy = TimeWindowStrategy(window_seconds=0.1)
        strategy.mark_automation_action()
        
        # Wait for window to expire
        time.sleep(0.2)
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        
        is_manual, reason = strategy.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        assert is_manual is True
        assert "outside automation window" in reason

    def test_integration_context_ignored(self):
        """Test that integration contexts are ignored."""
        context_id = "test_context_123"
        strategy = TimeWindowStrategy(integration_contexts={context_id})
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        
        context = Context()
        context.id = context_id
        
        is_manual, reason = strategy.is_manual_intervention(
            "light.test", old_state, new_state, context
        )
        
        assert is_manual is False
        assert reason is None


class TestCombinedStrategy:
    """Test CombinedStrategy class."""

    def test_combined_strategy_or_logic(self):
        """Test combined strategy with OR logic."""
        strategy1 = BrightnessThresholdStrategy()
        strategy2 = TimeWindowStrategy()
        
        combined = CombinedStrategy([strategy1, strategy2], logic="OR")
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 128}
        
        is_manual, reason = combined.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        # Should be True because brightness strategy detects it
        assert is_manual is True

    def test_combined_strategy_and_logic(self):
        """Test combined strategy with AND logic."""
        strategy1 = BrightnessThresholdStrategy()
        strategy2 = BrightnessThresholdStrategy()
        
        combined = CombinedStrategy([strategy1, strategy2], logic="AND")
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 128}
        
        is_manual, reason = combined.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        # Should be True because both strategies detect it
        assert is_manual is True

    def test_combined_strategy_and_logic_one_fails(self):
        """Test combined strategy with AND logic when one fails."""
        # Strategy 1 will detect manual, strategy 2 won't
        strategy1 = BrightnessThresholdStrategy()
        
        class AlwaysFalseStrategy(ManualInterventionStrategy):
            def is_manual_intervention(self, entity_id, old_state, new_state, context):
                return False, None
        
        strategy2 = AlwaysFalseStrategy()
        combined = CombinedStrategy([strategy1, strategy2], logic="AND")
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 128}
        
        is_manual, reason = combined.is_manual_intervention(
            "light.test", old_state, new_state, None
        )
        
        # Should be False because one strategy didn't detect it
        assert is_manual is False

    def test_combined_strategy_invalid_logic(self):
        """Test that invalid logic raises ValueError."""
        strategy1 = BrightnessThresholdStrategy()
        
        with pytest.raises(ValueError):
            CombinedStrategy([strategy1], logic="XOR")


class TestManualInterventionDetector:
    """Test ManualInterventionDetector class."""

    def test_detector_creation_default_strategy(self):
        """Test detector creation with default strategy."""
        detector = ManualInterventionDetector()
        assert detector is not None

    def test_detector_creation_custom_strategy(self):
        """Test detector creation with custom strategy."""
        strategy = BrightnessThresholdStrategy()
        detector = ManualInterventionDetector(strategy=strategy)
        assert detector._strategy == strategy

    def test_check_intervention_true(self):
        """Test check_intervention returns True for manual change."""
        detector = ManualInterventionDetector()
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 128}
        
        result = detector.check_intervention("light.test", old_state, new_state, None)
        assert result is True
        assert detector.get_last_reason() is not None

    def test_check_intervention_false(self):
        """Test check_intervention returns False for non-manual change."""
        detector = ManualInterventionDetector()
        
        old_state = MagicMock()
        old_state.state = "on"
        old_state.attributes = {"brightness": 128}
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 130}  # Small change
        
        result = detector.check_intervention("light.test", old_state, new_state, None)
        assert result is False

    def test_set_strategy(self):
        """Test set_strategy method."""
        detector = ManualInterventionDetector()
        
        new_strategy = TimeWindowStrategy()
        detector.set_strategy(new_strategy)
        
        assert detector._strategy == new_strategy

    def test_get_last_reason(self):
        """Test get_last_reason method."""
        detector = ManualInterventionDetector()
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 128}
        
        detector.check_intervention("light.test", old_state, new_state, None)
        
        reason = detector.get_last_reason()
        assert reason is not None
        assert "turned on manually" in reason

    def test_get_info(self):
        """Test get_info method."""
        detector = ManualInterventionDetector()
        
        info = detector.get_info()
        assert "strategy" in info
        assert "last_manual_reason" in info

    def test_add_strategy_to_detector(self):
        """Test adding strategies to detector (for extensibility)."""
        # This tests the pattern shown in the module
        detector = ManualInterventionDetector()
        brightness_strategy = BrightnessThresholdStrategy()
        
        # The ManualInterventionDetector supports adding strategies via set_strategy
        detector.set_strategy(brightness_strategy)
        
        old_state = MagicMock()
        old_state.state = "off"
        
        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {"brightness": 128}
        
        result = detector.check_intervention("light.test", old_state, new_state, None)
        assert result is True
