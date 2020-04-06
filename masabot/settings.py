# Handles settings registration and getting.
from typing import Dict, Any


class SettingsStore:
	"""
	A structure that holds mappings from keys to values and tracks their type. During writes, the values are checked to
	ensure that they follow the proper format as per the type of the key being written to.
	"""

	def __init__(self):
		self._registered_settings = {}

	def set_state(self, state_dict: Dict[str, Any]):
		self._registered_settings = dict(state_dict)

	def get_state(self) -> Dict[str, Any]:
		return dict(self._registered_settings)

	def create_percent_key(self, key: str, initial_value: float = 0.0):
		"""
		Create a new key with a value type of 'percent'. This will be a float that allows values between 0 and 1.
		:param key: The name of the new key.
		:param initial_value: The initial value of the new key. This will default to 0.0.
		"""
		if key in self._registered_settings:
			raise KeyError("key already exists in settings: " + repr(key))

		self._registered_settings[key] = {
			'type': 'percent',
			'value': 0.0
		}

		self.set(key, initial_value)

	def create_int_key(self, key: str, initial_value: int = 0):
		"""
		Create a new key with a value type of 'int'.
		:param key: The name of the new key.
		:param initial_value: The initial value of the new key. This will default to 0.
		"""
		if key in self._registered_settings:
			raise KeyError("key already exists in settings: " + repr(key))

		self._registered_settings[key] = {
			'type': 'percent',
			'value': 0
		}

		self.set(key, initial_value)

	def get_key_type(self, key: str) -> str:
		"""
		Get the type of a key. If the key does not currently exist, a KeyError is raised.
		:param key: The key to get the type of.
		:return: The type.
		"""
		if key not in self._registered_settings:
			raise KeyError("key does not exist in settings: " + repr(key))

		return self._registered_settings[key]['type']

	def get(self, key: str) -> Any:
		"""
		Get the current value of the given key. If the key does not currently exist, a KeyError is raised.

		:param key: The key whose value to get.
		:return: The value.
		"""
		if key not in self._registered_settings:
			raise KeyError("key does not exist in settings: " + repr(key))

		return self._registered_settings[key]['value']

	def set(self, key: str, value: Any):
		"""
		Set the value at a given key. The value is converted to the proper format and checked to ensure that it follows
		the proper format for the key. If the key does not exist, a KeyError is raised. If the value does not follow the
		proper format, a ValueError is raised.
		:param key: The key to write to.
		:param value: The new value to write.
		"""
		if key not in self._registered_settings:
			raise KeyError("key does not exist in settings: " + repr(key))

		setting_type = self._registered_settings[key]['type']

		if setting_type == 'percent':
			self._set_percent(key, value)
		elif setting_type == 'int':
			self._set_int(key, value)
		else:
			raise KeyError("key " + repr(key) + " has unknown type: " + repr(setting_type))

	def _set_percent(self, key: str, value: Any):
		try:
			float_val = float(value)
		except ValueError:
			raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 1")
		if float_val < 0.0 or float_val > 1.0:
			raise ValueError("That setting is a percentage, and has to be set to a number between 0 and 1")

		self._registered_settings[key]['value'] = float_val

	def _set_int(self, key: str, value: Any):
		try:
			int_val = int(value)
		except ValueError:
			raise ValueError("That setting is int-valued, and has to be set to a whole number")

		self._registered_settings[key]['value'] = int_val

	def __len__(self):
		return len(self._registered_settings)

	def __iter__(self):
		return iter(self._registered_settings)

	def __contains__(self, item):
		return item in self._registered_settings
