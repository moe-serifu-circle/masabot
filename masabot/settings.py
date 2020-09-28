# Handles settings registration and getting.
from typing import Dict, Any, Union
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
		try:
			int_val = int(value)
		except ValueError:
			raise ValueError("That setting is int-valued, and has to be set to a whole number")
		return int_val


class _PercentKeyType(_KeyType):
	def __init__(self):
		super().__init__(name='percent', default_default=0.0)

	def parse(self, value: str) -> float:
		try:
			float_val = float(value)
		except ValueError:
			raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 1")
		if float_val < 0.0 or float_val > 1.0:
			raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 1")
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


class Key:
	def __init__(self, key_type: _KeyType, name: str, **kwargs):
		self.name = name
		self.type = key_type
		if 'default' in kwargs:
			self.default = self.type.parse(kwargs['default'])
		else:
			self.default = self.type.default_default

	def parse(self, value: str) -> Any:
		return self.type.parse(value)

	def clone(self) -> 'Key':
		return Key(self.type, self.name, default=self.default)


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

	def get_key_type(self, key: str) -> str:
		"""
		Get the type of a key. If the key does not currently exist, a KeyError is raised.
		:param key: The key to get the type of.
		:return: The type.
		"""
		if key not in self._registered_keys:
			raise KeyError("key does not exist in settings: " + repr(key))

		return self._registered_keys[key].type.name

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
