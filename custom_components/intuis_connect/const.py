"""Constants for the Intuis Connect integration (v1.1.1)."""

DOMAIN = "intuis_connect"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# ---------------------------------------------------------------------------
# Default durations / temperatures (all editable in the Options flow)
# ---------------------------------------------------------------------------
DEFAULT_MANUAL_DURATION = 120   # minutes – manual override
DEFAULT_AWAY_DURATION   = 1440  # minutes – 24 h away
DEFAULT_BOOST_DURATION  = 30    # minutes – quick boost
DEFAULT_AWAY_TEMP       = 16.0  # °C
DEFAULT_BOOST_TEMP      = 30.0  # °C (radiator max)

# ---------------------------------------------------------------------------
# API hosts
# Intuis has two production clusters; we try the first, fall back to the second
# ---------------------------------------------------------------------------
BASE_URLS = [
    "https://app.muller-intuitiv.net",
    "https://app-prod.intuis-sas.com",
]

# Keep a primary BASE_URL for code paths that expect one string
BASE_URL = BASE_URLS[0]

# End-point paths (kept simple for readability)
AUTH_PATH      = "/oauth2/token"
HOMESDATA_PATH = "/api/homesdata"
HOMESTATUS_PATH= "/syncapi/v1/homestatus"
SETSTATE_PATH  = "/syncapi/v1/setstate"

# Derive full URLs (legacy code still imports these)
AUTH_URL          = f"{BASE_URL}{AUTH_PATH}"
API_GET_HOMESDATA = f"{BASE_URL}{HOMESDATA_PATH}"
API_GET_HOME_STATUS = f"{BASE_URL}{HOMESTATUS_PATH}"
API_SET_STATE     = f"{BASE_URL}{SETSTATE_PATH}"

# OAuth meta
CLIENT_ID     = "59e604638fe283fd4dc7e353"
CLIENT_SECRET = "ZW2vL8czEkn87zemtR1h1ZB0ZVwoeR"
AUTH_SCOPE    = "read_muller write_muller"
USER_PREFIX   = "muller"

# App identification headers mimicking the mobile app
APP_TYPE    = "app_muller"
APP_VERSION = "1108100"

# ---------------------------------------------------------------------------
# Presets exposed to Home Assistant
# ---------------------------------------------------------------------------
PRESET_SCHEDULE = "schedule"
PRESET_AWAY     = "away"
PRESET_BOOST    = "boost"

SUPPORTED_PRESETS = [PRESET_SCHEDULE, PRESET_AWAY, PRESET_BOOST]
