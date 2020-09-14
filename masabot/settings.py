# Handles settings registration and getting.
from typing import Dict, Any, Union


def _get_default(type: str):
	if type == 'percent':
		return 0.0
	elif type == 'int:':
		return 0
	else:
		return None

class SettingsStore:
	"""
	A structure that holds mappings from keys to values and tracks their type. During writes, the values are checked to
	ensure that they follow the proper format as per the type of the key being written to.
	"""

	def __init__(self):
		self._registered_keys = {}
		""":type: Dict[str, str]"""

		self._settings = {}
		""":type: Dict[int, Dict[str, Union[int, str, bool, float]]]"""

	def set_state(self, server: int, state_dict: Dict[str, Any]):
		self._settings[server] = dict(state_dict)

	def set_global_state(self, state_dict: Dict[str, Any]):
		for k in state_dict:
			v = state_dict[k]
			self._registered_keys[k] = str(v)

	def get_global_state(self) -> Dict[str, str]:
		return dict(self._registered_keys)

	def get_state(self, server: int) -> Dict[str, Any]:
		if server not in self._settings:
			self._settings[server] = {}
			for k in self._registered_keys:
				key_type = self._registered_keys[k]
				default = _get_default(key_type)
				self._settings[server][k] = default
		return dict(self._settings[server])

	def create_percent_key(self, key: str, initial_value: float = 0.0):
		"""
		Create a new key with a value type of 'percent'. This will be a float that allows values between 0 and 1.
		:param key: The name of the new key.
		:param initial_value: The initial value of the new key. This will default to 0.0.
		"""
		if key in self._registered_keys:
			raise KeyError("key already exists in settings: " + repr(key))

		self._registered_keys[key] = 'percent'

		for server in self._settings:
			self.set(server, key, initial_value)

	def create_int_key(self, key: str, initial_value: int = 0):
		"""
		Create a new key with a value type of 'int'.
		:param key: The name of the new key.
		:param initial_value: The initial value of the new key. This will default to 0.
		"""
		if key in self._registered_keys:
			raise KeyError("key already exists in settings: " + repr(key))

		self._registered_keys[key] = 'int'

		for server in self._settings:
			self.set(server, key, initial_value)

	def get_key_type(self, key: str) -> str:
		"""
		Get the type of a key. If the key does not currently exist, a KeyError is raised.
		:param key: The key to get the type of.
		:return: The type.
		"""
		if key not in self._registered_keys:
			raise KeyError("key does not exist in settings: " + repr(key))

		return self._registered_keys[key]

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
				key_type = self._registered_keys[k]
				default = _get_default(key_type)
				self._settings[server][k] = default

		return self._settings[key]

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

		setting_type = self._registered_keys[key]

		if setting_type == 'percent':
			self._set_percent(server, key, value)
		elif setting_type == 'int':
			self._set_int(server, key, value)
		else:
			raise KeyError("key " + repr(key) + " has unknown type: " + repr(setting_type))

	def _set_percent(self, server: int, key: str, value: Any):
		try:
			float_val = float(value)
		except ValueError:
			raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 1")
		if float_val < 0.0 or float_val > 1.0:
			raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 1")

		self._settings[server][key] = float_val

	def _set_int(self, server: int, key: str, value: Any):
		try:
			int_val = int(value)
		except ValueError:
			raise ValueError("That setting is int-valued, and has to be set to a whole number")

		self._settings[server][key] = int_val

	def __len__(self):
		return len(self._registered_keys)

	def __iter__(self):
		return iter(self._registered_keys)

	def __contains__(self, item):
		return item in self._registered_keys
