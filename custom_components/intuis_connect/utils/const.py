"""Constants for Intuis Connect integration (v1.9.6)."""

DOMAIN = "intuis_connect"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_HOME_ID = "home_id"
CONF_HOME_NAME = "home_name"

DEFAULT_UPDATE_INTERVAL = 2 # minutes

# Default override / preset settings (editable in Options flow later)
DEFAULT_MANUAL_DURATION = 60  # minutes (1 hour)
DEFAULT_AWAY_DURATION = 240  # minutes (4 hours)
DEFAULT_BOOST_DURATION = 30  # minutes
DEFAULT_AWAY_TEMP = 16.0  # °C
DEFAULT_BOOST_TEMP = 22.0  # °C

# API clusters
BASE_URLS: list[str] = [
    "https://app.muller-intuitiv.net",
    "https://app-prod.intuis-sas.com",
]
BASE_URL: str = BASE_URLS[0]  # used for legacy constants

# Endpoint paths
AUTH_PATH: str = "/oauth2/token"
HOMESDATA_PATH = "/api/homesdata"
HOMESTATUS_PATH = "/syncapi/v1/homestatus"
CONFIG_PATH = "/syncapi/v1/getconfigs"
SETSTATE_PATH = "/syncapi/v1/setstate"
HOMEMEASURE_PATH = "/api/gethomemeasure"
ROOMMEASURE_PATH = "/api/getroommeasure"

# Energy measure types - request all tariffs to capture all consumption
# Extended with heating/hot_water types discovered from APK decompilation
ENERGY_MEASURE_TYPES = (
    "sum_energy_elec,sum_energy_elec$0,sum_energy_elec$1,sum_energy_elec$2,"
    "sum_energy_elec_heating,sum_energy_elec_hot_water"
)

ENERGY_BASE = f"{BASE_URL}/api"
GET_SCHEDULE_PATH = "/gethomeschedule"
SET_SCHEDULE_PATH = "/updatenewhomeschedule"
DELETE_SCHEDULE_PATH = "/deletenewhomeschedule"
SWITCH_SCHEDULE_PATH = "/switchhomeschedule"
SYNCHOMESCHEDULE_PATH = "/api/synchomeschedule"

# Legacy full URLs so imports keep working
AUTH_URL = f"{BASE_URL}{AUTH_PATH}"
API_GET_HOMESDATA = f"{BASE_URL}{HOMESDATA_PATH}"
API_GET_HOME_STATUS = f"{BASE_URL}{HOMESTATUS_PATH}"
API_SET_STATE = f"{BASE_URL}{SETSTATE_PATH}"

# OAuth / app identification
CLIENT_ID = "59e604638fe283fd4dc7e353"
CLIENT_SECRET = "ZW2vL8czEkn87zemtR1h1ZB0ZVwoeR"
AUTH_SCOPE = "read_muller write_muller"
USER_PREFIX = "muller"

APP_TYPE = "app_muller"
APP_VERSION = "1108100"

# Presets
PRESET_SCHEDULE = "schedule"
PRESET_AWAY = "away"
PRESET_BOOST = "boost"
SUPPORTED_PRESETS: list[str] = [PRESET_SCHEDULE, PRESET_AWAY, PRESET_BOOST]

# Options
CONF_MANUAL_DURATION = "manual_duration"
CONF_AWAY_DURATION = "away_duration"
CONF_BOOST_DURATION = "boost_duration"
CONF_AWAY_TEMP = "away_temp"
CONF_BOOST_TEMP = "boost_temp"
CONF_INDEFINITE_MODE = "indefinite_mode"
DEFAULT_INDEFINITE_MODE = False

# Duration options for dropdown selectors (value in minutes, label for display)
# 12-hour max is a hardware limit for manual/boost modes
DURATION_OPTIONS_SHORT = [
    {"value": "15", "label": "15 minutes"},
    {"value": "30", "label": "30 minutes"},
    {"value": "60", "label": "1 hour"},
    {"value": "120", "label": "2 hours"},
    {"value": "240", "label": "4 hours"},
    {"value": "360", "label": "6 hours"},
    {"value": "480", "label": "8 hours"},
    {"value": "720", "label": "12 hours (max)"},
]

# Away mode allows longer durations
DURATION_OPTIONS_LONG = [
    {"value": "60", "label": "1 hour"},
    {"value": "120", "label": "2 hours"},
    {"value": "240", "label": "4 hours"},
    {"value": "480", "label": "8 hours"},
    {"value": "720", "label": "12 hours"},
    {"value": "1440", "label": "1 day"},
    {"value": "4320", "label": "3 days"},
    {"value": "10080", "label": "1 week"},
]

# Energy scale options
CONF_ENERGY_SCALE = "energy_scale"
DEFAULT_ENERGY_SCALE = "1day"
ENERGY_SCALE_OPTIONS = {
    "5min": "5 minutes (real-time)",
    "30min": "30 minutes",
    "1hour": "1 hour",
    "1day": "1 day (daily total)",
}

# Energy reset hour (when daily counters reset)
CONF_ENERGY_RESET_HOUR = "energy_reset_hour"
DEFAULT_ENERGY_RESET_HOUR = 2  # 2 AM - after API has finalized previous day's data

# Historical energy import options
CONF_IMPORT_HISTORY = "import_history"
CONF_IMPORT_HISTORY_DAYS = "import_history_days"
DEFAULT_IMPORT_HISTORY = False
DEFAULT_IMPORT_HISTORY_DAYS = 365

IMPORT_DAYS_OPTIONS = [
    {"value": "30", "label": "30 days (1 month)"},
    {"value": "90", "label": "90 days (3 months)"},
    {"value": "180", "label": "180 days (6 months)"},
    {"value": "365", "label": "365 days (1 year)"},
    {"value": "730", "label": "730 days (2 years)"},
]

# API modes
API_MODE_OFF = "off"
API_MODE_HOME = "home"
API_MODE_AUTO = "auto"
API_MODE_MANUAL = "manual"
API_MODE_AWAY = "away"
API_MODE_BOOST = "boost"

# Rate limiting configuration
CONF_RATE_LIMIT_DELAY = "rate_limit_delay"
CONF_CIRCUIT_BREAKER_THRESHOLD = "circuit_breaker_threshold"
CONF_MIN_REQUEST_DELAY = "min_request_delay"
CONF_MAX_UPDATE_INTERVAL = "max_update_interval"

# Rate limiting defaults
DEFAULT_RATE_LIMIT_DELAY = 30         # seconds - initial delay on 429
DEFAULT_CIRCUIT_THRESHOLD = 3         # consecutive 429s before circuit opens
DEFAULT_MIN_REQUEST_DELAY = 0.5       # seconds between requests
DEFAULT_MAX_UPDATE_INTERVAL = 10      # minutes - max polling interval when rate limited
DEFAULT_RATE_LIMIT_MAX_DELAY = 60     # seconds - max delay (reduced to avoid bootstrap timeout)
DEFAULT_RATE_LIMIT_ATTEMPTS = 5       # retry attempts for rate limited requests

# Rate limit options for UI
RATE_LIMIT_DELAY_OPTIONS = [
    {"value": "10", "label": "10 seconds"},
    {"value": "30", "label": "30 seconds (default)"},
    {"value": "60", "label": "1 minute"},
    {"value": "120", "label": "2 minutes"},
]

CIRCUIT_THRESHOLD_OPTIONS = [
    {"value": "1", "label": "1 (aggressive)"},
    {"value": "3", "label": "3 (default)"},
    {"value": "5", "label": "5 (relaxed)"},
    {"value": "10", "label": "10 (very relaxed)"},
]

MAX_UPDATE_INTERVAL_OPTIONS = [
    {"value": "5", "label": "5 minutes"},
    {"value": "10", "label": "10 minutes (default)"},
    {"value": "15", "label": "15 minutes"},
    {"value": "30", "label": "30 minutes"},
]
