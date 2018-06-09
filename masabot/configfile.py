# converts json to config

import json
import logging


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


def load_config(json_path):
	with open(json_path, "r") as f:
		config = json.load(f)
	
	if 'prefix' not in config:
		_log.warning("No prefix in config; defaulting to '!'")
		config['prefix'] = '!'

	if 'discord-api-key' not in config:
		raise ValueError("Required key 'discord-api-key' not in configuration file '" + json_path + "'")
	if config['discord-api-key'] == '':
		raise ValueError("Required key 'discord-api-key' is empty in configuration file '" + json_path + "'")

	if 'announce-channels' not in config:
		_log.warning("No announce-channels in config; defaulting to none.")
		config['announce-channels'] = []

	return config
