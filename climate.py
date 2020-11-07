"""
Platform for Floureon thermostat integration. Weback cloud access based.

configuration.yaml:
    climate:
      - platform: floureon-cloud
        login:
        password:
        device:


Example:
    climate:
      - platform: floureon-cloud
	login: +49-1234 ...
	password: xxxx
	device: by-t03-00-11-22 ...
"""

import json
import logging
import threading

from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
from homeassistant.helpers.entity import Entity
from homeassistant.components.climate import ClimateEntity, HVAC_MODE_HEAT, HVAC_MODE_OFF, SUPPORT_TARGET_TEMPERATURE
from weback_unofficial.client import WebackApi


logger = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform."""

    login = config.get("login")
    password = config.get("password")
    device = config.get("device")
    name = config.get("name")

    if login is None:
        logger.error("invalid login!")
        return False

    if password is None:
        logger.error("invalid password!")
        return False

    if device is None:
        logger.error("invalid device!")
        return False

    if device is None:
        logger.error("invalid name!")
        return False

    add_entities([Thermostat(login, password, device, name)])

    return True


class Thermostat(ClimateEntity):
    def __init__(self, login, password, device, name):
        self._current_temperature = None
        self._target_temperature = None
        self._is_on = False

        self._login = login
        self._password = password
        self._device = device
        self._name = name

        self._device = Device(login, password, device)
        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def supported_features(self):
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def hvac_mode(self):
        if self._is_on:
            return HVAC_MODE_HEAT
        return HVAC_MODE_OFF

    @property
    def hvac_modes(self):
        return [HVAC_MODE_HEAT, HVAC_MODE_OFF]

    def set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVAC_MODE_HEAT:
            self.turn_on()
        else:
            self.turn_off()

    @property
    def should_poll(self):
        return True

    @property
    def current_temperature(self):
        return self._current_temperature

    @property
    def target_temperature_low(self):
        return 15.0

    @property
    def target_temperature_high(self):
        return 30.0

    @property
    def target_temperature_step(self):
        return 0.5

    @property
    def target_temperature(self):
        return self._target_temperature

    @property
    def is_on(self):
        return _is_on

    def set_temperature(self, **kwargs):
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            temp = kwargs.get(ATTR_TEMPERATURE)
            self._device.set_temperature(temp)

    def turn_on(self):
        self._device.manual()
        self._device.turn_on()

    def turn_off(self):
        self._device.manual()
        self._device.turn_off()

    def update(self):
        self._current_temperature = self._device.current_temperature()
        self._target_temperature = self._device.target_temperature()
        self._is_on = self._device.is_on()
        logger.info(f"Read current temp: {self._current_temperature}")
        logger.info(f"Read target temp: {self._target_temperature}")
        logger.info(f"Read is on: {self._is_on}")


class Device:
    def __init__(self, login, password, device_name):
        self._login = login
        self._password = password
        self._device_name = device_name
        self._topic = f"$aws/things/{device_name}/shadow/update"

        self._weback = None

        self._lock = threading.Lock()
        self._weback = WebackApi(self._login, self._password)

    def _client(self):
        session = self._weback.get_session()
        return session.client('iot-data')

    def shadow(self):
        self._lock.acquire()
        resp = self._client().get_thing_shadow(thingName=self._device_name)
        self._lock.release()
        shadow = json.loads(resp['payload'].read())
        return shadow

    def current_temperature(self):
        result = self.shadow()
        return result['state']['reported']['air_tem'] / 10

    def target_temperature(self):
        result = self.shadow()
        return result['state']['reported']['set_tem'] / 2

    def is_on(self):
        result = self.shadow()
        return result['state']['reported']['working_status'] == "on"

    def turn_on(self):
        self._command('working_status', 'on')

    def turn_off(self):
        self._command('working_status', 'off')

    def auto(self):
        self._command('workmode', 'auto')

    def manual(self):
        self._command('workmode', 'hand')

    def set_temperature(self, temp):
        self._command('set_tem', temp * 2)

    def _command(self, command, status):
        payload = {
            'state': {
                'desired': {
                    command: status
                }
            }
        }
        self._lock.acquire()
        resp = self._client().publish(topic=self._topic, qos = 0, payload = json.dumps(payload))
        self._lock.release()
        try:
            if int(resp['ResponseMetadata']['HTTPStatusCode']) == 200:
                return True
        except Exception as e:
            logger.exception(e)
