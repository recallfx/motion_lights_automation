"""Constants for the Motion lights automation integration."""

DOMAIN = "motion_lights_automation"

# Configuration keys
CONF_MOTION_ENTITY = "motion_entity"
CONF_LIGHTS = "lights"
CONF_NO_MOTION_WAIT = "no_motion_wait"
CONF_OVERRIDE_SWITCH = "override_switch"
CONF_BRIGHTNESS_ACTIVE = "brightness_active"  # Brightness when house/room is active
CONF_BRIGHTNESS_INACTIVE = (
    "brightness_inactive"  # Brightness when house/room is inactive
)
CONF_AMBIENT_LIGHT_SENSOR = (
    "ambient_light_sensor"  # Lux sensor or binary sensor for ambient light detection
)
CONF_AMBIENT_LIGHT_THRESHOLD = (
    "ambient_light_threshold"  # Lux threshold for lux sensors (default 50)
)
CONF_HOUSE_ACTIVE = "house_active"  # Switch/input_boolean for house active state

# New configuration options for continuous monitoring
CONF_MOTION_ACTIVATION = "motion_activation"  # Enable/disable motion-based control
CONF_EXTENDED_TIMEOUT = "extended_timeout"  # Time before lights turn off
CONF_MOTION_DELAY = (
    "motion_delay"  # Delay before turning on lights after motion detected
)

# Default values
DEFAULT_NO_MOTION_WAIT = 300
DEFAULT_BRIGHTNESS_ACTIVE = 80
DEFAULT_BRIGHTNESS_INACTIVE = 10
DEFAULT_AMBIENT_LIGHT_THRESHOLD = 50  # Lux threshold with ±20 hysteresis (30-70 lux)

# New defaults
DEFAULT_MOTION_ACTIVATION = True  # Motion detection enabled by default
DEFAULT_EXTENDED_TIMEOUT = 1200  # 20 minutes before lights turn off
DEFAULT_MOTION_DELAY = 0  # No delay by default (instant response)


# State constants (public strings used by sensors/diagnostics)
# Keep this as the single source of truth for states used across the integration.
STATE_OVERRIDDEN = "overridden"  # override=ON, ignore everything, no timers
STATE_IDLE = "idle"  # override=OFF, no lights on
STATE_MOTION_AUTO = "motion-auto"  # motion=ON, automation in control
STATE_MOTION_MANUAL = "motion-manual"  # motion=ON, user has taken control
STATE_AUTO = "auto"  # motion=OFF, MotionTimer running (automation lights on)
STATE_MANUAL = "manual"  # motion=OFF, ExtendedTimer running (user lights on)
STATE_MANUAL_OFF = "manual-off"  # lights turned OFF manually during AUTO, temporary override blocks auto-on until ExtendedTimer expires
