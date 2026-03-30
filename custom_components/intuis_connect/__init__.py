"""Setup for Intuis Connect (v1.10.0)."""
from __future__ import annotations

import asyncio
import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.storage import Store

from .intuis_api.api import IntuisAPI, InvalidAuth, CannotConnect, APIError
from .utils.const import (
    DOMAIN,
    CONF_REFRESH_TOKEN,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_IMPORT_HISTORY,
    CONF_IMPORT_HISTORY_DAYS,
    CONF_HOURLY_STATS_ENABLED,
    CONF_HOURLY_STATS_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_HOURLY_STATS_ENABLED,
    DEFAULT_HOURLY_STATS_INTERVAL,
    CONF_RATE_LIMIT_DELAY,
    CONF_CIRCUIT_BREAKER_THRESHOLD,
    CONF_MIN_REQUEST_DELAY,
    CONF_MAX_UPDATE_INTERVAL,
    DEFAULT_RATE_LIMIT_DELAY,
    DEFAULT_CIRCUIT_THRESHOLD,
    DEFAULT_MIN_REQUEST_DELAY,
    DEFAULT_MAX_UPDATE_INTERVAL,
    CONF_ENERGY_RESET_HOUR,
    DEFAULT_ENERGY_RESET_HOUR,
    CONF_ENERGY_COST_ENABLED,
    DEFAULT_ENERGY_COST_ENABLED,
)
from .entity.intuis_entity import IntuisDataUpdateCoordinator
from .history_import import (
    HistoryImportManager,
    async_import_energy_history,
)
from .hourly_stats import HourlyStatsUpdater
from .cost_stats import CostStatsUpdater
from .intuis_data import IntuisData
from .services import (
    async_generate_services_yaml,
    async_register_services,
    SERVICE_SWITCH_SCHEDULE,
    SERVICE_REFRESH_SCHEDULES,
    SERVICE_SET_SCHEDULE_SLOT,
    SERVICE_SET_ZONE_TEMPERATURE,
    SERVICE_IMPORT_ENERGY_HISTORY,
    ATTR_SCHEDULE_NAME,
    ATTR_DAY,
    ATTR_START_DAY,
    ATTR_END_DAY,
    ATTR_START_TIME,
    ATTR_END_TIME,
    ATTR_ZONE_NAME,
    ATTR_ROOM_NAME,
    ATTR_TEMPERATURE,
    ATTR_DAYS,
)

_LOGGER = logging.getLogger(__name__)

# Storage for persisting overrides across restarts
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.overrides"

PLATFORMS: list[Platform] = [
    Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
]


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Reloading entry %s due to options update", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_migrate_cost_entity_ids(hass, entry, intuis_home) -> None:
    """Migrate old energy_cost/_2 entities to the new 'cost' suffix.

    Previous versions named cost sensors 'sensor.X_energy_cost' which
    conflicts with the virtual entity HA's Energy Dashboard auto-creates.
    New name: 'sensor.X_cost' (unique_id suffix: 'cost').

    This migration:
    1. Looks for entities with old unique_id suffix '_energy_cost' or '_energy_cost_2'
    2. Renames them in the entity registry to the new entity_id 'sensor.X_cost'
    3. Renames the StatisticsMeta row to the new statistic_id
    4. Removes any HA-generated virtual 'sensor.X_energy_cost' (state=unavailable)
    """
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.db_schema import StatisticsMeta, Statistics, StatisticsShortTerm
    from homeassistant.helpers.recorder import session_scope
    from homeassistant.helpers import entity_registry as er
    from sqlalchemy import delete, update, select

    ent_reg = er.async_get(hass)
    instance = get_instance(hass)

    rooms = intuis_home.rooms if intuis_home else {}
    migrated = 0

    for room_id in rooms:
        room = rooms[room_id]
        room_slug = room.name.lower().replace(" ", "_").replace("-", "_")

        # New target entity_id and unique_id
        new_entity_id = f"sensor.{room_slug}_cost"
        new_unique_id = f"intuis_{intuis_home.id}_{room_id}_cost"

        # Skip if already migrated
        if ent_reg.async_get_entity_id("sensor", DOMAIN, new_unique_id):
            continue

        # Find old entity: try _energy_cost then _energy_cost_2
        old_unique_id = f"intuis_{intuis_home.id}_{room_id}_energy_cost"
        old_entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if not old_entity_id:
            # Check _2 variant (old unique_id may have been duplicated)
            old_entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, old_unique_id + "_2")

        if not old_entity_id:
            continue

        # Remove any blocking HA-generated virtual entity at our target entity_id
        blocking_entry = ent_reg.async_get(new_entity_id)
        if blocking_entry and blocking_entry.platform != DOMAIN:
            try:
                ent_reg.async_remove(new_entity_id)
                _LOGGER.info("Migration: removed HA-generated virtual entity '%s'", new_entity_id)
            except Exception as e:
                _LOGGER.warning("Migration: could not remove blocking entity '%s': %s", new_entity_id, e)

        # Rename StatisticsMeta old → new
        def _rename_stats(old_sid: str, new_sid: str) -> bool:
            with session_scope(session=instance.get_session()) as session:
                meta = session.execute(
                    select(StatisticsMeta).where(StatisticsMeta.statistic_id == old_sid)
                ).scalar_one_or_none()
                if meta:
                    session.execute(
                        update(StatisticsMeta)
                        .where(StatisticsMeta.statistic_id == old_sid)
                        .values(statistic_id=new_sid)
                    )
                    return True
                return False

        try:
            renamed = await instance.async_add_executor_job(
                _rename_stats, old_entity_id, new_entity_id
            )
            if renamed:
                _LOGGER.info("Migration: renamed StatisticsMeta '%s' → '%s'",
                             old_entity_id, new_entity_id)
        except Exception as e:
            _LOGGER.warning("Migration: could not rename StatisticsMeta '%s': %s", old_entity_id, e)

        # Update entity registry: new unique_id + new entity_id
        try:
            ent_reg.async_update_entity(
                old_entity_id,
                new_entity_id=new_entity_id,
                new_unique_id=new_unique_id,
            )
            _LOGGER.info("Migration: entity '%s' (unique_id=%s) → '%s' (unique_id=%s)",
                         old_entity_id, old_unique_id, new_entity_id, new_unique_id)
            migrated += 1
        except Exception as e:
            _LOGGER.warning("Migration: could not rename entity '%s': %s", old_entity_id, e)

    if migrated:
        _LOGGER.info("Migration: migrated %d cost entities to 'cost' suffix", migrated)



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Intuis Connect from a config entry."""
    _LOGGER.debug("Setting up entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(update_listener))

    # ---------- setup API ----------------------------------------------------------
    session = async_get_clientsession(hass)

    # Get rate limit options from config
    rate_limit_delay = entry.options.get(CONF_RATE_LIMIT_DELAY, DEFAULT_RATE_LIMIT_DELAY)
    circuit_threshold = entry.options.get(CONF_CIRCUIT_BREAKER_THRESHOLD, DEFAULT_CIRCUIT_THRESHOLD)
    min_request_delay = entry.options.get(CONF_MIN_REQUEST_DELAY, DEFAULT_MIN_REQUEST_DELAY)
    max_update_interval = entry.options.get(CONF_MAX_UPDATE_INTERVAL, DEFAULT_MAX_UPDATE_INTERVAL)

    intuis_api = IntuisAPI(
        session,
        home_id=entry.data["home_id"],
        rate_limit_delay=rate_limit_delay,
        circuit_threshold=circuit_threshold,
        min_request_delay=min_request_delay,
    )
    intuis_api.refresh_token = entry.data[CONF_REFRESH_TOKEN]

    try:
        await intuis_api.async_refresh_access_token()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed from err
    except CannotConnect as err:
        raise ConfigEntryNotReady from err

    intuis_home = await intuis_api.async_get_homes_data()
    _LOGGER.debug("Intuis home: %s", intuis_home.__str__())

    # ---------- generate dynamic services.yaml -------------------------------------
    await async_generate_services_yaml(hass, intuis_home)

    # ---------- shared overrides (sticky intents) with persistence -----------------
    # Set up storage for persisting overrides across restarts
    store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")

    # Load persisted overrides
    stored_data = await store.async_load()
    overrides: dict[str, dict] = stored_data.get("overrides", {}) if stored_data else {}

    if overrides:
        _LOGGER.info("Loaded %d persisted overrides from storage", len(overrides))

    # Callback to save overrides to storage
    async def save_overrides() -> None:
        """Persist overrides to storage."""
        await store.async_save({"overrides": overrides})
        _LOGGER.debug("Saved %d overrides to storage", len(overrides))

    # ---------- setup coordinator --------------------------------------------------
    # Callback to get current options from config entry
    def get_options() -> dict:
        return dict(entry.options)

    intuis_data = IntuisData(
        intuis_api,
        intuis_home,
        overrides,
        get_options,
        save_overrides_callback=save_overrides,
    )

    coordinator: IntuisDataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=intuis_data.async_update,
        update_interval=datetime.timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
    )

    # Set up adaptive polling callback for rate limiting
    def on_rate_limit() -> None:
        """Handle rate limit event by increasing update interval."""
        current_minutes = coordinator.update_interval.total_seconds() / 60
        new_minutes = min(current_minutes * 2, max_update_interval)
        if new_minutes > current_minutes:
            coordinator.update_interval = datetime.timedelta(minutes=new_minutes)
            _LOGGER.warning(
                "Rate limited. Increased update interval from %.0f to %.0f minutes",
                current_minutes, new_minutes
            )

    intuis_api.set_rate_limit_callback(on_rate_limit)

    # Schedule periodic recovery of update interval
    async def recover_update_interval(_now=None) -> None:
        """Gradually recover update interval after successful updates."""
        if not intuis_api.circuit_breaker.is_open:
            current_minutes = coordinator.update_interval.total_seconds() / 60
            if current_minutes > DEFAULT_UPDATE_INTERVAL:
                new_minutes = max(current_minutes - 1, DEFAULT_UPDATE_INTERVAL)
                coordinator.update_interval = datetime.timedelta(minutes=new_minutes)
                _LOGGER.info(
                    "Recovering update interval from %.0f to %.0f minutes",
                    current_minutes, new_minutes
                )

    # Store recovery function for later use
    intuis_data.set_success_callback(recover_update_interval)

    await coordinator.async_config_entry_first_refresh()

    # ---------- store everything ---------------------------------------------------
    _LOGGER.debug("Storing data for entry %s", entry.entry_id)
    hass.data[DOMAIN][entry.entry_id] = {
        "api": intuis_api,
        "coordinator": coordinator,
        "intuis_home": intuis_home,
        "overrides": overrides,
        "save_overrides": save_overrides,
    }
    _LOGGER.debug("Stored data for entry %s", entry.entry_id)

    # ---------- migrate orphaned _energy_cost entities (_2 fix) -------------------
    # Previous versions may have left a StatisticsMeta entry occupying the clean
    # entity_id (e.g. sensor.chambre_parents_energy_cost), causing the new sensor
    # to be registered as sensor.chambre_parents_energy_cost_2.
    # Migration: remove the orphaned StatisticsMeta rows so the new entity can
    # claim the clean entity_id on the next reload.
    cost_enabled = entry.options.get(CONF_ENERGY_COST_ENABLED, DEFAULT_ENERGY_COST_ENABLED)
    if cost_enabled:
        await _async_migrate_cost_entity_ids(hass, entry, intuis_home)

    # ---------- setup platforms ----------------------------------------------------
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ---------- register services -------------------------------------------------
    await async_register_services(hass, entry)

    # ---------- cancel any previous import and trigger new one if requested --------
    # Cancel any existing import from previous session to release resources
    if "import_managers" in hass.data.get(DOMAIN, {}):
        existing_manager = hass.data[DOMAIN]["import_managers"].get(entry.entry_id)
        if existing_manager and existing_manager.is_running:
            _LOGGER.info("Cancelling previous import that was still running")
            existing_manager.cancel()

    import_history = entry.options.get(CONF_IMPORT_HISTORY, False)
    import_days = entry.options.get(CONF_IMPORT_HISTORY_DAYS, 0)

    if import_history and import_days > 0:
        _LOGGER.info(
            "Historical energy import requested for %d days, starting in background",
            import_days,
        )

        # Create import manager
        manager = HistoryImportManager(hass, entry.entry_id)
        await manager.async_load()

        # Store manager for potential service access
        if "import_managers" not in hass.data[DOMAIN]:
            hass.data[DOMAIN]["import_managers"] = {}
        hass.data[DOMAIN]["import_managers"][entry.entry_id] = manager

        # Start import in background task
        hass.async_create_task(
            async_import_energy_history(
                hass=hass,
                api=intuis_api,
                intuis_home=intuis_home,
                manager=manager,
                days=import_days,
                room_filter=None,
                home_id=entry.data["home_id"],
            )
        )

        # Clear the import flag so it doesn't run again on reload
        new_options = {**entry.options, CONF_IMPORT_HISTORY: False}
        hass.config_entries.async_update_entry(entry, options=new_options)

    # ---------- start hourly stats updater ------------------------------------------
    # HourlyStatsUpdater - Periodic import of hourly energy statistics
    # This runs periodically to fetch hourly energy data and inject it into HA statistics
    hourly_stats_enabled = entry.options.get(
        CONF_HOURLY_STATS_ENABLED, DEFAULT_HOURLY_STATS_ENABLED
    )
    hourly_stats_interval = entry.options.get(
        CONF_HOURLY_STATS_INTERVAL, DEFAULT_HOURLY_STATS_INTERVAL
    )
    
    if hourly_stats_enabled:
        # Get timezone from HA config or default to Europe/Paris
        timezone_str = hass.config.time_zone or "Europe/Paris"
        
        hourly_stats_updater = HourlyStatsUpdater(
            hass=hass,
            api=intuis_api,
            intuis_home=intuis_home,
            entry_id=entry.entry_id,
            home_id=entry.data["home_id"],
            update_interval_minutes=hourly_stats_interval,
            timezone_str=timezone_str,
        )
        hass.data[DOMAIN][entry.entry_id]["hourly_stats_updater"] = hourly_stats_updater
        # Load storage NOW so base_kwh is available before sensors start reporting
        await hourly_stats_updater.load_storage()

        # CostStatsUpdater — wired to HourlyStatsUpdater so cost is updated
        # at the same cadence as energy stats.
        cost_enabled = entry.options.get(CONF_ENERGY_COST_ENABLED, DEFAULT_ENERGY_COST_ENABLED)
        if cost_enabled:
            cost_updater = CostStatsUpdater(
                hass=hass,
                intuis_home=intuis_home,
                entry_id=entry.entry_id,
                options=dict(entry.options),
                timezone_str=timezone_str,
            )
            await cost_updater.load_storage()
            cost_updater.publish_cost_base()
            hourly_stats_updater.cost_updater = cost_updater
            hass.data[DOMAIN][entry.entry_id]["cost_stats_updater"] = cost_updater
            _LOGGER.info("Energy cost statistics updater enabled")

        await hourly_stats_updater.async_start()
        
        # Schedule daily rebase at reset_hour+1 local time.
        # reset_hour is the API's finalization time (default 02:00, configurable).
        # Running 1h after ensures J-1 data is fully available in the API.
        _LOGGER.info(
            "Hourly energy statistics updater started (interval: %d min, tz: %s)",
            hourly_stats_interval,
            timezone_str,
        )
    else:
        _LOGGER.debug("Hourly energy statistics updater disabled by configuration")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    
    # Stop hourly stats updater
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    hourly_stats_updater = entry_data.get("hourly_stats_updater")
    if hourly_stats_updater:
        await hourly_stats_updater.async_stop()
        _LOGGER.debug("Stopped hourly stats updater for entry %s", entry.entry_id)
    
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to a newer version.

    Handles migration from V2 to V3:
    - Adds CONF_HOME_NAME if missing (for multi-home support)
    """
    _LOGGER.debug("Migrating entry %s from version %s", entry.entry_id, entry.version)

    if entry.version < 3:
        # V2 -> V3: Add home_name if missing
        new_data = {**entry.data}

        if CONF_HOME_NAME not in new_data or not new_data.get(CONF_HOME_NAME):
            home_id = new_data.get(CONF_HOME_ID, "")
            home_name = None

            # Try to fetch the home name from the API
            try:
                session = async_get_clientsession(hass)
                api = IntuisAPI(session, home_id=home_id)
                api.refresh_token = new_data.get(CONF_REFRESH_TOKEN)
                await api.async_refresh_access_token()

                homes = await api.async_get_all_homes()
                for home in homes:
                    if home["id"] == home_id:
                        home_name = home["name"]
                        break

                _LOGGER.info(
                    "Migration: Fetched home name '%s' for home %s",
                    home_name,
                    home_id,
                )
            except (InvalidAuth, CannotConnect, APIError) as err:
                _LOGGER.warning(
                    "Migration: Could not fetch home name from API: %s",
                    err,
                )
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Migration: Timeout while fetching home name from API"
                )
            except Exception as err:
                _LOGGER.warning(
                    "Migration: Unexpected error fetching home name: %s",
                    err,
                )

            # Fall back to truncated home_id if API fails
            if not home_name:
                home_name = f"Home {home_id[:8]}" if home_id else "Unknown Home"
                _LOGGER.info(
                    "Migration: Using fallback home name '%s'",
                    home_name,
                )

            new_data[CONF_HOME_NAME] = home_name

        hass.config_entries.async_update_entry(
            entry,
            data=new_data,
            version=3,
        )
        _LOGGER.info(
            "Migrated entry %s to version 3 with home_name: %s",
            entry.entry_id,
            new_data.get(CONF_HOME_NAME),
        )

    return True
