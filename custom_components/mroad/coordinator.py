"""Periodic account updates."""
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MRoadClient, MRoadError, MRoadAuthError
from .const import DOMAIN, CONF_INTERVAL, DEFAULT_INTERVAL


class MRoadCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: MRoadClient):
        super().__init__(
            hass, logging.getLogger(__name__), name=DOMAIN, config_entry=entry,
            update_interval=timedelta(minutes=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        )
        self.client = client

    async def _async_update_data(self):
        try:
            return await self.client.async_accounts()
        except MRoadAuthError:
            raise ConfigEntryAuthFailed("Authentication rejected") from None
        except MRoadError as err:
            raise UpdateFailed(str(err)) from None
