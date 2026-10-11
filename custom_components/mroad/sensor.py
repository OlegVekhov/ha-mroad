"""Balance and account status sensors."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import callback

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    @callback
    def add_accounts():
        entities = []
        for account_id in coordinator.data or {}:
            if account_id not in known:
                known.add(account_id)
                entities.extend(MRoadSensor(coordinator, entry, account_id, kind) for kind in ("balance", "status"))
        if entities:
            async_add_entities(entities)

    add_accounts()
    entry.async_on_unload(coordinator.async_add_listener(add_accounts))


class MRoadSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, account_id, kind):
        super().__init__(coordinator)
        self.account_id = account_id
        self.kind = kind
        number = coordinator.data[account_id]["number"]
        self._attr_unique_id = f"{entry.unique_id}_{account_id}_{kind}"
        self._attr_translation_key = kind
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}_{account_id}")},
            name=f"Главная дорога {number}", manufacturer="Главная дорога",
            model="Лицевой счёт", configuration_url="https://lk.m-road.ru/",
        )
        if kind == "balance":
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = "RUB"
            self._attr_suggested_display_precision = 2
            self._attr_icon = "mdi:wallet"
        else:
            self._attr_icon = "mdi:card-account-details-outline"

    @property
    def available(self):
        return super().available and self.account_id in (self.coordinator.data or {})

    @property
    def native_value(self):
        account = (self.coordinator.data or {}).get(self.account_id)
        return account.get(self.kind) if account else None

    @property
    def extra_state_attributes(self):
        account = (self.coordinator.data or {}).get(self.account_id)
        if not account:
            return {}
        return {"account_number": account["number"], "status_id": account["status_id"]}
