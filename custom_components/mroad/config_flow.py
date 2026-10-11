"""Configure and reauthenticate through the Home Assistant UI."""
import hashlib
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import MRoadClient, MRoadError, MRoadAuthError
from .const import DOMAIN, CONF_INTERVAL, DEFAULT_INTERVAL


def schema(username=""):
    return vol.Schema({
        vol.Required(CONF_USERNAME, default=username): str,
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    })


class MRoadConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, data):
        data[CONF_USERNAME] = data[CONF_USERNAME].strip()
        client = MRoadClient(async_get_clientsession(self.hass), data[CONF_USERNAME], data[CONF_PASSWORD])
        await client.async_accounts()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self._validate(user_input)
            except MRoadAuthError:
                errors["base"] = "invalid_auth"
            except MRoadError:
                errors["base"] = "cannot_connect"
            else:
                identifier = hashlib.sha256(user_input[CONF_USERNAME].encode()).hexdigest()
                await self.async_set_unique_id(identifier)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Главная дорога", data=user_input)
        return self.async_show_form(step_id="user", data_schema=schema(), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            if user_input[CONF_USERNAME].strip() != entry.data[CONF_USERNAME]:
                errors["base"] = "wrong_account"
            else:
                try:
                    await self._validate(user_input)
                except MRoadAuthError:
                    errors["base"] = "invalid_auth"
                except MRoadError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema(entry.data[CONF_USERNAME]), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return MRoadOptionsFlow()


class MRoadOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_INTERVAL, default=self.config_entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)):
                vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
        }))
