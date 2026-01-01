"""Constants for Intuis Connect integration (v1.3.0)."""

DOMAIN = "intuis_connect"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_HOME_ID = "home_id"

DEFAULT_UPDATE_INTERVAL = 2 # minutes

# Default override / preset settings (editable in Options flow later)
DEFAULT_MANUAL_DURATION = 5  # minutes
DEFAULT_AWAY_DURATION = 1440  # minutes
DEFAULT_BOOST_DURATION = 30  # minutes
DEFAULT_AWAY_TEMP = 16.0  # °C
DEFAULT_BOOST_TEMP = 30.0  # °C

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
ENERGY_MEASURE_TYPES = "sum_energy_elec,sum_energy_elec$0,sum_energy_elec$1,sum_energy_elec$2"

ENERGY_BASE = "https://connect.intuis.net/api"
GET_SCHEDULE_PATH = "/gethomeschedule"
SET_SCHEDULE_PATH = "/updatenewhomeschedule"
DELETE_SCHEDULE_PATH = "/deletenewhomeschedule"
SWITCH_SCHEDULE_PATH = "/switchhomeschedule"

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

# Energy scale options
CONF_ENERGY_SCALE = "energy_scale"
DEFAULT_ENERGY_SCALE = "1day"
ENERGY_SCALE_OPTIONS = {
    "5min": "5 minutes (real-time)",
    "30min": "30 minutes",
    "1hour": "1 hour",
    "1day": "1 day (daily total)",
}

# Historical import options
CONF_IMPORT_HISTORY = "import_history"
CONF_HISTORY_DAYS = "history_days"
DEFAULT_IMPORT_HISTORY = False
DEFAULT_HISTORY_DAYS = 30
HISTORY_DAYS_OPTIONS = {
    "7": "7 days",
    "30": "30 days",
    "90": "90 days",
    "365": "1 year",
}

# API modes
API_MODE_OFF = "off"
API_MODE_HOME = "home"
API_MODE_AUTO = "auto"
API_MODE_MANUAL = "manual"
API_MODE_AWAY = "away"
API_MODE_BOOST = "boost"
