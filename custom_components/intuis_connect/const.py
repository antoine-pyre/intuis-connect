"""Constants for the Intuis Connect integration."""

DOMAIN = "intuis_connect"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Default values
DEFAULT_MANUAL_DURATION = 120  # in minutes
DEFAULT_UPDATE_INTERVAL = 300  # in seconds

# API constants
CLIENT_ID = "59e604638fe283fd4dc7e353"
CLIENT_SECRET = "ZW2vL8czEkn87zemtR1h1ZB0ZVwoeR"
BASE_URL = "https://app.muller-intuitiv.net"
AUTH_URL = f"{BASE_URL}/oauth2/token"
API_GET_HOMESDATA = f"{BASE_URL}/api/homesdata"
API_GET_HOME_STATUS = f"{BASE_URL}/syncapi/v1/homestatus"
API_SET_STATE = f"{BASE_URL}/syncapi/v1/setstate"

# Auth scope and prefix for OAuth2
AUTH_SCOPE = "read_muller write_muller"
USER_PREFIX = "muller"

# App identification (to mimic official Intuis app)
APP_TYPE = "app_muller"
APP_VERSION = "1108100"
