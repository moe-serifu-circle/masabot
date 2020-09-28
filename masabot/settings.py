# Handles settings registration and getting.
from typing import Dict, Any, Union, Optional
import logging

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class _KeyType:
	def __init__(self, name: str, default_default: Union[int, str, bool, float]):
		self.name = name
		self.default_default = default_default

	# noinspection PyMethodMayBeStatic
	def parse(self, value: str) -> Any:
		return NotImplementedError("do not use _KeyType directly")


class _IntKeyType(_KeyType):
	def __init__(self):
		super().__init__(name='int', default_default=0)

	def parse(self, value: str) -> int:
		value = str(value)
		try:
			int_val = int(value)
		except ValueError:
			raise ValueError("That setting is int-valued, and has to be set to a whole number")
		return int_val


class _IntRangeKeyType(_KeyType):
	def __init__(self, min_allowed: Optional[int] = None, max_allowed: Optional[int] = None):
		if min_allowed is not None and max_allowed is not None and int(min_allowed) >= int(max_allowed):
			raise ValueError("min_allowed must be less than max_allowed if both are specified")
		if min_allowed is None and max_allowed is None:
			raise ValueError("both min_allowed and max_allowed cannot be unspecified; use _IntKeyType for that")

		range_name = "int-range"
		if min_allowed is not None:
			range_name += "[" + str(int(min_allowed)) + ", "
		else:
			range_name += "(-INF, "
		if max_allowed is not None:
			range_name += str(int(max_allowed)) + "]"
		else:
			range_name += "INF)"

		zero_val = 0
		if min_allowed is not None and int(min_allowed) > zero_val:
			zero_val = int(min_allowed)
		if max_allowed is not None and int(max_allowed) < zero_val:
			zero_val = int(max_allowed)

		super().__init__(name=range_name, default_default=zero_val)
		self.min: Optional[int] = None
		self.max: Optional[int] = None

		if min_allowed is not None:
			self.min = int(min_allowed)
		if max_allowed is not None:
			self.max = int(max_allowed)

	def parse(self, value: str) -> int:
		value = str(value)
		try:
			int_val = int(value)
		except ValueError:
			raise ValueError("That setting is int-valued, and has to be set to a whole number")

		if self.min is not None and int_val < self.min:
			raise ValueError("That setting has to be set to at least " + repr(self.min))

		if self.max is not None and int_val > self.max:
			raise ValueError("That setting can't be any bigger than " + repr(self.min))

		return int_val


class _PercentKeyType(_KeyType):
	def __init__(self):
		super().__init__(name='percent', default_default=0.0)

	def parse(self, value: str) -> float:
		value = str(value)
		if value.endswith("%"):
			value = value[:-1]
			try:
				fval = float(value)
			except ValueError:
				raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 100 when using %")
			if fval < 0 or fval > 100:
				raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 100 when using %")
			value = fval / 100.0

		try:
			float_val = float(value)
		except ValueError:
			raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 1")
		if float_val < 0.0 or float_val > 1.0:
			raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 1")
		return float_val


class _FloatKeyType(_KeyType):
	def __init__(self):
		super().__init__(name='float', default_default=0.0)

	def parse(self, value: str) -> float:
		value = str(value)
		try:
			float_val = float(value)
		except ValueError:
			raise ValueError("That setting has to be set to a number")
		if float_val < 0.0 or float_val > 1.0:
			raise ValueError("That setting has to be set to a number")
		return float_val


class _FloatRangeKeyType(_KeyType):
	def __init__(self, min_allowed: Optional[float] = None, max_allowed: Optional[float] = None):
		if min_allowed is not None and max_allowed is not None and float(min_allowed) >= float(max_allowed):
			raise ValueError("min_allowed must be less than max_allowed if both are specified")
		if min_allowed is None and max_allowed is None:
			raise ValueError("both min_allowed and max_allowed cannot be unspecified; use _FloatKeyType for that")
		if min_allowed is not None and max_allowed is not None and float(min_allowed) == 0.0 and float(max_allowed) == 1.0:
			raise ValueError("float range between 0 and 1 is a percent; use _PercentKeyType for that")

		range_name = "float-range"
		if min_allowed is not None:
			range_name += "[" + str(float(min_allowed)) + ", "
		else:
			range_name += "(-INF, "
		if max_allowed is not None:
			range_name += str(float(max_allowed)) + "]"
		else:
			range_name += "INF)"

		zero_val = 0
		if min_allowed is not None and float(min_allowed) > zero_val:
			zero_val = float(min_allowed)
		if max_allowed is not None and float(max_allowed) < zero_val:
			zero_val = float(max_allowed)

		super().__init__(name=range_name, default_default=zero_val)
		self.min: Optional[float] = None
		self.max: Optional[float] = None

		if min_allowed is not None:
			self.min = float(min_allowed)
		if max_allowed is not None:
			self.max = float(max_allowed)

	def parse(self, value: str) -> float:
		value = str(value)
		try:
			float_val = float(value)
		except ValueError:
			raise ValueError("That setting has to be set to a number")

		if self.min is not None and float_val < self.min:
			raise ValueError("That setting has to be set to at least " + repr(self.min))

		if self.max is not None and float_val > self.max:
			raise ValueError("That setting can't be any bigger than " + repr(self.min))

		return float_val


class _StringKeyType(_KeyType):
	def __init__(self):
		super().__init__(name='string', default_default="")

	def parse(self, value: str) -> str:
		return str(value)


# set up some singletons here; using oo so we can get parse() polymorphism
key_type_int = _IntKeyType()
key_type_percent = _PercentKeyType()
key_type_string = _StringKeyType()
key_type_float = _FloatKeyType()


def key_type_int_range(min: Optional[int] = None, max: Optional[int] = None):
	return _IntRangeKeyType(min, max)


def key_type_float_range(min: Optional[float] = None, max: Optional[float] = None):
	return _FloatRangeKeyType(min, max)


# TODO: incorporate context limitations in the key obj itself instead of maintaining a key metadata in core
# TODO: incorporate standardized setting help by allowing keys to give a help string.
class Key:
	def __init__(self, key_type: _KeyType, name: str, **kwargs):
		"""
		Create a new Key.

		:param key_type: The type of the key.
		:param name: The name of the key.
		:param kwargs: The following additional options are supported:
		`default` - Set the default for the key.
		`prompt_before` - Gives a string to have as the prompt before it is updated. Default, with none specified
		is to require no prompt.
		`call_module_on_alter` - Specifies that the module on_settings_change should be called when the value
		is updated. Default is False.
		"""
		self.name = name
		self.type = key_type
		if 'default' in kwargs:
			self.default = self.type.parse(kwargs['default'])
		else:
			self.default = self.type.default_default
		self.prompt_before: Optional[str] = kwargs.get('prompt_before', None)
		self.call_module_on_alter: bool = kwargs.get('call_module_on_alter', False)

	def __str__(self):
		msg = "Key[{:s}, {:s}, default={!r}, prompt_before={:s}, call_on_alter={:s}]"
		prompt_text = "True" if self.prompt_before is not None else "False"
		on_alter_text = "True" if self.call_module_on_alter else "False"
		return msg.format(self.type.name, self.name, self.default, prompt_text, on_alter_text)

	def parse(self, value: str) -> Any:
		return self.type.parse(value)

	def clone(self) -> 'Key':
		return Key(
			self.type,
			self.name,
			default=self.default,
			prompt_before=self.prompt_before,
			call_module_on_alter=self.call_module_on_alter
		)



class SettingsStore:
	"""
	A structure that holds mappings from keys to values and tracks their type. During writes, the values are checked to
	ensure that they follow the proper format as per the type of the key being written to.
	"""

	def __init__(self):
		self._registered_keys = {}
		""":type: Dict[str, _Key]"""

		self._settings = {}
		""":type: Dict[int, Dict[str, Union[int, str, bool, float]]]"""

		self._global_settings = {}
		""":type: Dict[str, Union[int, str, bool, float]]"""

	def set_global_state(self, state_dict: Dict[str, Any]):
		self._global_settings = {k: v for k, v in state_dict.items() if k in self._registered_keys}

	def set_state(self, server: int, state_dict: Dict[str, Any]):
		self._settings[server] = {k: v for k, v in state_dict.items() if k in self._registered_keys}

	def get_state(self, server: int) -> Dict[str, Any]:
		if server not in self._settings:
			self._settings[server] = {}
			for k in self._registered_keys:
				key = self._registered_keys[k]
				self._settings[server][k] = key.default
		return dict(self._settings[server])

	def get_global_state(self) -> Dict[str, Any]:
		return dict(self._global_settings)

	def register_key(self, key: Key):
		"""
		Register an existing key with this settings store. If any servers already exist, they are instantly updated to
		all have a value for the key equal to the default value of the key.
		:param key: The key to be registered. If a key with the same name already exists, it is replaced.
		"""
		self._registered_keys[key.name] = key
		self.set_all(key.name, key.default)

	def get_key(self, key_name: str) -> Key:
		"""
		Get the Key object for a given key name. If the key does not currently exist, a KeyError is raised.
		:param key_name: The name of the Key to get.
		:return: The key.
		"""
		if key_name not in self._registered_keys:
			raise KeyError("key does not exist in settings: " + repr(key_name))

		return self._registered_keys[key_name]

	def get(self, server: int, key: str) -> Any:
		"""
		Get the current value of the given key. If the key does not currently exist, a KeyError is raised.

		:param server: The server to get the key in.
		:param key: The key whose value to get.
		:return: The value.
		"""
		if key not in self._registered_keys:
			raise KeyError("key does not exist in settings: " + repr(key))

		if server not in self._settings:
			self._settings[server] = {}

		if key not in self._settings[server]:
			for k in self._registered_keys:
				key_obj = self._registered_keys[k]
				self._settings[server][k] = key_obj.default

		return self._settings[server][key]

	def get_global(self, key: str) -> Any:
		"""
		Get the current value of the given key in the global store. If the key does not currently exist, a KeyError is raised.
		:param key: The key whose value to get.
		:return: The value.
		"""
		if key not in self._registered_keys:
			raise KeyError("key does not exist in settings: " + repr(key))

		if key not in self._global_settings:
			for k in self._registered_keys:
				key_obj = self._registered_keys[k]
				self._global_settings[k] = key_obj.default
		return self._global_settings[key]

	def set(self, server: int, key: str, value: Any):
		"""
		Set the value at a given key. The value is converted to the proper format and checked to ensure that it follows
		the proper format for the key. If the key does not exist, a KeyError is raised. If the value does not follow the
		proper format, a ValueError is raised.
		:param server: server to set key for.
		:param key: The key to write to.
		:param value: The new value to write.
		"""
		if key not in self._registered_keys:
			raise KeyError("key does not exist in settings: " + repr(key))

		if server not in self._settings:
			self._settings[server] = {}

		key_obj = self._registered_keys[key]
		self._settings[server][key] = key_obj.parse(value)

	def set_global(self, key: str, value: Any):
		if key not in self._registered_keys:
			raise KeyError("key does not exist in settings: " + repr(key))

		key_obj = self._registered_keys[key]
		self._global_settings[key] = key_obj.parse(value)

	def set_all(self, key: str, value: Any):
		"""
		Set the value in all severs and in the global settings.
		:param key: The key to write to.
		:param value: The new value to write.
		"""
		for server in self._settings:
			self.set(server, key, value)
		self.set_global(key, value)

	def __len__(self):
		return len(self._registered_keys)

	def __iter__(self):
		return iter(self._registered_keys)

	def __contains__(self, item):
		return item in self._registered_keys
