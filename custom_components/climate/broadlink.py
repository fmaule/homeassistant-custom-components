import asyncio
import logging
import binascii
import socket
import os.path
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.components.climate import (ClimateDevice, PLATFORM_SCHEMA)
from homeassistant.const import (TEMP_CELSIUS, TEMP_FAHRENHEIT, ATTR_TEMPERATURE, CONF_NAME, CONF_HOST, CONF_MAC, CONF_TIMEOUT, CONF_CUSTOMIZE)
from configparser import ConfigParser
from base64 import b64encode, b64decode

REQUIREMENTS = ['broadlink==0.5']

_LOGGER = logging.getLogger(__name__)

CONF_IRCODES_INI = 'ircodes_ini'
CONF_MIN_TEMP = 'min_temp'
CONF_MAX_TEMP = 'max_temp'
CONF_TARGET_TEMP = 'target_temp'
CONF_OPERATIONS = 'operations'
CONF_FAN_MODES = 'fan_modes'
CONF_DEFAULT_OPERATION = 'default_operation'
CONF_DEFAULT_FAN_MODE = 'default_fan_mode'

DEFAULT_NAME = 'Broadlink IR Climate'
DEFAULT_TIMEOUT = 10
DEFAULT_RETRY = 3
DEFAULT_MIN_TEMP = 16
DEFAULT_MAX_TEMP = 30
DEFAULT_TARGET_TEMP = 20
DEFAULT_OPERATION_LIST = ['Off', 'Heat', 'Cool', 'Auto']
DEFAULT_FAN_MODE_LIST = ['Low', 'Mid', 'High', 'Auto']
DEFAULT_OPERATION = 'Off'
DEFAULT_FAN_MODE = 'Auto'

CUSTOMIZE_SCHEMA = vol.Schema({
    vol.Optional(CONF_OPERATIONS): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(CONF_FAN_MODES): vol.All(cv.ensure_list, [cv.string])
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Required(CONF_IRCODES_INI): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int, 
    vol.Optional(CONF_MIN_TEMP, default=DEFAULT_MIN_TEMP): cv.positive_int,
    vol.Optional(CONF_MAX_TEMP, default=DEFAULT_MAX_TEMP): cv.positive_int,
    vol.Optional(CONF_TARGET_TEMP, default=DEFAULT_TARGET_TEMP): cv.positive_int,
    vol.Optional(CONF_CUSTOMIZE, default={}): CUSTOMIZE_SCHEMA,
    vol.Optional(CONF_DEFAULT_OPERATION, default=DEFAULT_OPERATION): cv.string,
    vol.Optional(CONF_DEFAULT_FAN_MODE, default=DEFAULT_FAN_MODE): cv.string
})

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up the Broadlink IR Climate platform."""
    name = config.get(CONF_NAME)
    ip_addr = config.get(CONF_HOST)
    mac_addr = binascii.unhexlify(config.get(CONF_MAC).encode().replace(b':', b''))
    
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)
    target_temp = config.get(CONF_TARGET_TEMP)
    operation_list = config.get(CONF_CUSTOMIZE).get(CONF_OPERATIONS, []) or DEFAULT_OPERATION_LIST
    fan_list = config.get(CONF_CUSTOMIZE).get(CONF_FAN_MODES, []) or DEFAULT_FAN_MODE_LIST
    default_operation = config.get(CONF_DEFAULT_OPERATION)
    default_fan_mode = config.get(CONF_DEFAULT_FAN_MODE)
    
    import broadlink
    
    broadlink_device = broadlink.rm((ip_addr, 80), mac_addr)
    broadlink_device.timeout = config.get(CONF_TIMEOUT)

    try:
        broadlink_device.auth()
    except socket.timeout:
        _LOGGER.error("Failed to connect to Broadlink RM Device")
    
    
    ircodes_ini_file = config.get(CONF_IRCODES_INI)
    
    if ircodes_ini_file.startswith("/"):
        ircodes_ini_file = ircodes_ini_file[1:]
        
    ircodes_ini_path = hass.config.path(ircodes_ini_file)
    
    if os.path.exists(ircodes_ini_path):
        ircodes_ini = ConfigParser()
        ircodes_ini.read(ircodes_ini_path)
    else:
        _LOGGER.error("The ini file was not found. (" + ircodes_ini_path + ")")
        return
    
    
    async_add_devices([
        BroadlinkIRClimate(name, broadlink_device, ircodes_ini, min_temp, max_temp, target_temp, operation_list, fan_list, default_operation, default_fan_mode)
    ])

class BroadlinkIRClimate(ClimateDevice):

    def __init__(self, name, broadlink_device, ircodes_ini, min_temp, max_temp, target_temp, operation_list, fan_list, default_operation, default_fan_mode):
                 
        """Initialize the Broadlink IR Climate device."""
        self._name = name
        
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._target_temperature = target_temp
        self._target_temperature_step = 1
        self._unit_of_measurement = TEMP_CELSIUS
        
        self._current_temperature = 0

        self._current_operation = default_operation
        self._current_fan_mode = default_fan_mode
        
        self._operation_list = operation_list
        self._fan_list = fan_list
                
        self._broadlink_device = broadlink_device
        self._commands_ini = ircodes_ini
    
    
    def send_ir(self):     
        section = self._current_operation.lower()
        value = self._current_fan_mode.lower() + "_" + str(int(self._target_temperature)) if not section == 'off' else 'off_command'
        command = self._commands_ini.get(section, value)
        
        for retry in range(DEFAULT_RETRY):
            try:
                payload = b64decode(command)
                self._broadlink_device.send_data(payload)
                break
            except (socket.timeout, ValueError):
                try:
                    self._broadlink_device.auth()
                except socket.timeout:
                    if retry == DEFAULT_RETRY-1:
                        _LOGGER.error("Failed to send packet to Broadlink RM Device")
        
        
    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature
        
    @property
    def min_temp(self):
        """Return the polling state."""
        return self._min_temp
        
    @property
    def max_temp(self):
        """Return the polling state."""
        return self._max_temp    
        
    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature
        
    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return self._target_temperature_step

    @property
    def current_operation(self):
        """Return current operation ie. heat, cool, idle."""
        return self._current_operation

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return self._operation_list

    @property
    def current_fan_mode(self):
        """Return the fan setting."""
        return self._current_fan_mode

    @property
    def fan_list(self):
        """Return the list of available fan modes."""
        return self._fan_list

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            self._target_temperature = kwargs.get(ATTR_TEMPERATURE)
            
        if self._current_operation.lower() != 'off':
            self.send_ir()
            
        self.schedule_update_ha_state()

    def set_fan_mode(self, fan):
        """Set new target temperature."""
        self._current_fan_mode = fan
        
        if self._current_operation.lower() != 'off':
            self.send_ir()
            
        self.schedule_update_ha_state()

    def set_operation_mode(self, operation_mode):
        """Set new target temperature."""
        if operation_mode == 'idle':
            self._current_operation = 'Off'
        else:
            self._current_operation = operation_mode
        
        self.send_ir()
        self.schedule_update_ha_state()
