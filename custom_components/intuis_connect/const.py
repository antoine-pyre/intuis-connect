"""Constants for the Intuis Connect integration."""
DOMAIN = "intuis_connect"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

DEFAULT_MANUAL_DURATION = 120   # minutes
DEFAULT_AWAY_DURATION = 1440    # minutes
DEFAULT_BOOST_DURATION = 30     # minutes
DEFAULT_AWAY_TEMP = 16.0
DEFAULT_BOOST_TEMP = 30.0

BASE_URLS = [
    "https://app.muller-intuitiv.net",
    "https://app-prod.intuis-sas.com",
]
BASE_URL = BASE_URLS[0]

AUTH_PATH = "/oauth2/token"
HOMESDATA_PATH = "/api/homesdata"
HOMESTATUS_PATH = "/syncapi/v1/homestatus"
SETSTATE_PATH = "/syncapi/v1/setstate"

AUTH_URL = f"{BASE_URL}{AUTH_PATH}"
API_GET_HOMESDATA = f"{BASE_URL}{HOMESDATA_PATH}"
API_GET_HOME_STATUS = f"{BASE_URL}{HOMESTATUS_PATH}"
API_SET_STATE = f"{BASE_URL}{SETSTATE_PATH}"

CLIENT_ID = "59e604638fe283fd4dc7e353"
CLIENT_SECRET = "ZW2vL8czEkn87zemtR1h1ZB0ZVwoeR"
AUTH_SCOPE = "read_muller write_muller"
USER_PREFIX = "muller"

APP_TYPE = "app_muller"
APP_VERSION = "1108100"

PRESET_SCHEDULE = "schedule"
PRESET_AWAY = "away"
PRESET_BOOST = "boost"
SUPPORTED_PRESETS = [PRESET_SCHEDULE, PRESET_AWAY, PRESET_BOOST]
