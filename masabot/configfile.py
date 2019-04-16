# converts json to config

import json
import logging
import os


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


def load_config(json_path):
	"""
	Load config from the json file given. Environment variables for secrets override any config file values.
	:type json_path: str
	:param json_path: The path to the config file.
	:rtype: dict[str, Any]
	:return: The map containing all configuration settings.
	"""
	with open(json_path, "r") as f:
		config = json.load(f)

	if os.environ.get("MASABOT_DISCORD_API_KEY", None) is not None:
		config['discord-api-key'] = os.environ["MASABOT_DISCORD_API_KEY"]
	if os.environ.get("MASABOT_ANIMELIST__ANILIST_CLIENT_ID", None) is not None:
		config['animelist']['anilist-client-id'] = os.environ["MASABOT_ANIMELIST__ANILIST_CLIENT_ID"]
	if os.environ.get("MASABOT_ANIMELIST__ANILIST_CLIENT_SECRET", None) is not None:
		config['animelist']['anilist-client-secret'] = os.environ["MASABOT_ANIMELIST__ANILIST_CLIENT_SECRET"]
	if os.environ.get("MASABOT_ANNOUNCE_CHANNELS", None) is not None:
		config['announce-channels'] = os.environ['MASABOT_ANNOUNCE_CHANNELS'].split(',')

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

	if 'modules' not in config:
		_log.warning("No module configurations found")
		config['modules'] = {}

	return config
