import datetime
import os.path
import logging
import pathlib

from typing import Optional, Sequence, Tuple, Dict, Union, List, Any

import discord

from .. import util, settings as masabotsettings
from ..pluginapi import PluginAPI

__all__ = [
	'karma',
	'animeme',
	'translate',
	'roll',
	'animelist',
	'noticeme',
	'ratewaifu',
	'sparkle',
	'rolemanager',
	'headpat',
	'customroles',
]


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


def mention_target_any():
	return {'target_type': 'any'}


def mention_target_specific(
		*user_ids: Tuple[int, ...],
		role_ids: Optional[Sequence[int]] = None,
		channel_ids: Optional[Sequence[int]] = None):
	return {'target_type': 'specific', 'users': user_ids, 'roles': role_ids, 'channels': channel_ids}


def mention_target_self():
	return {'target_type': 'self'}


class MentionTrigger(object):
	def __init__(self, target=None):
		self.trigger_type = 'MENTION'
		if target is None:
			self.mention_targets = mention_target_self()
		else:
			self.mention_targets = target


class InvocationTrigger(object):
	def __init__(self, invocation):
		self.trigger_type = 'INVOCATION'
		self.invocation = invocation


class RegexTrigger(object):
	def __init__(self, regex):
		self.trigger_type = 'REGEX'
		self.regex = regex


class TimerTrigger(object):
	"""NOTE: TIMERS ARE NEVER SAVED AS PART OF STATE AND ARE ALWAYS RECREATED"""
	def __init__(self, days=0, seconds=0, minutes=0, hours=0, weeks=0):
		self.trigger_type = 'TIMER'
		dt = datetime.timedelta(days=days, seconds=seconds, minutes=minutes, hours=hours, weeks=weeks)
		self.timer_duration = dt


class ReactionTrigger(object):
	"""
	emoji is list of single emoji by grapheme sequence, not name.
	if name is required to recognize (e.g. for a custom emote), put it in custom_emoji list.
	blank emoji and blank custom_emoji will receive ALL reactions in the server.

	custom_emoji entries apply only to the ones in this server.
	"""

	def __init__(
			self, emoji: List[str] = None, custom_emoji: List[str] = None, reacts: bool = True, unreacts: bool = False
	):
		self.trigger_type = 'REACTION'

		if emoji is None:
			emoji = list()
		if custom_emoji is None:
			custom_emoji = list()
		self.emoji = emoji
		self.custom_emoji = custom_emoji
		self.include_react_remove = unreacts
		self.include_react_add = reacts


class BotBehaviorModule(object):
	def __init__(
			self,
			name: str,
			desc: str,
			help_text: str,
			triggers: Sequence[Union[InvocationTrigger, RegexTrigger, MentionTrigger, TimerTrigger, ReactionTrigger]],
			resource_root: str,
			save_state_on_trigger: bool = False,
			settings: Optional[Sequence[masabotsettings.Key]] = None,
			global_settings: Optional[Sequence[masabotsettings.Key]] = None,
			server_only_settings: Optional[Sequence[masabotsettings.Key]] = None,
	):
		"""
		Create a new BotBehaviorModule instance.

		:param name: The name of the module. Must be unique among all loaded modules.
		:param desc: A brief description of what the command does. Should fit on a single line. This is displayed next
		to the command when `help` lists all modules.
		:param help_text: A full help text including all information on the command. This is shown when the help for
		this particular module is displayed.
		:param triggers: All possible triggers that cause this module to be executed.
		:param resource_root: The root directory that resources are to be placed in.
		:param save_state_on_trigger: Whether this module wishes to have state auto-saved on every handle. If this is
		true, then the module should define get_state() and set_state() methods for saving state to a dict and setting
		state from a dict (also global versions of those, get_global_state() and set_global_state()).
		:param settings: Settings keys that this module uses. There will be a value for each key for every server that
		the bot runs in, as well as a separate 'global' value that is used in non-server contexts.
		:param global_settings: Settings keys that this module uses that have only a single value across all servers that this
		module is active in.
		:param server_only_settings: Settings keys that this module uses that have only values for the servers that it is
		in, and has no value in a non-server context.
		"""
		self.help_text = help_text
		self.description = desc
		self.name = name
		self.save_state_on_trigger = save_state_on_trigger
		self.triggers = triggers
		self.per_server_settings_keys: List[masabotsettings.Key] = []
		self.global_settings_keys: List[masabotsettings.Key] = []
		self.server_only_settings_keys: List[masabotsettings.Key] = []

		if settings is not None:
			self.per_server_settings_keys = [k.clone() for k in settings]
		if global_settings is not None:
			self.global_settings_keys = [k.clone() for k in global_settings]
		if server_only_settings is not None:
			self.server_only_settings_keys = [k.clone() for k in server_only_settings]

		self._resource_dir: str = os.path.join(resource_root, name)
		if not os.path.exists(self._resource_dir):
			os.mkdir(self._resource_dir)

	def remove_resource(self, resource):
		"""
		Removes an existing resource. If the resource does not already exist, this function has no effect.

		:type resource: str
		:param resource: The resource to remove.
		"""
		path = os.path.normpath(resource)
		full_path = os.path.join(self._resource_dir, path)
		if os.path.exists(full_path):
			os.remove(full_path)

	def open_resource(self, resource, for_writing=False):
		"""
		Open a resource in binary mode and get the file pointer for it. All resources are opened in binary mode; if text
		mode is needed, module state should be used instead.

		All resources exist within a generic 'resource store'; each module has its own separate resource store that
		no other module can access. The specific details of how the resource store functions is up to the
		implementation, and callers should not rely on such details. The current implementation stores resources as
		files on the filesystem, but this may change in the future.

		The resource should be given as relative to the module's resource store, which is automatically set up by this
		module and can be depended on to already exist. I.e. If a module needed the resource located in
		<module_store>/images/my_image.png, the path "images/my_image.png" should be used. The 'flavor' of path used is
		platform-agnostic; unix-style paths should always be used.

		:type resource: str
		:param resource: The path to the resource to open.
		:type for_writing: bool
		:param for_writing: Whether to open the resource for writing instead. Defaults to False.
		Defaults to False.
		:rtype: io.BytesIO
		:return: The file like object ready for use.
		"""
		if resource.endswith('/'):
			raise ValueError("Resource cannot end in a '/' character.")
		if resource.startswith('/'):
			raise ValueError("Resource cannot start with a '/' character.")

		path = os.path.normpath(resource)

		if for_writing:
			self._create_resource_dirs(path)
			mode = 'wb'
		else:
			mode = 'rb'

		full_path = os.path.join(self._resource_dir, path)
		return open(full_path, mode)

	def list_resources(self, pattern='**/*'):
		"""
		List the paths to all resources that this module has access to.

		:type pattern: str
		:param pattern: Limits the returned resources to those that match the globbing pattern. '**' is any number of
		sub-paths. By default, this is set to '**/*', which returns all resources, but it can be changed to another
		pattern to alter what is returned; e.g. "**/*.txt" would return all resources that end in .txt, and "*.txt"
		would return all resources that end in '.txt' that are not in a sub-path.
		:rtype: list[str]
		:return: A list of the paths of all resources that currently exist, and are accessible to this module.
		"""
		return pathlib.Path(self._resource_dir).glob(pattern)

	def load_config(self, config):
		pass

	def get_state(self, server: int) -> Dict:
		"""
		If server is not a server that the module has a state for, return a default state.
		:param server:
		:return:
		"""
		pass

	def set_state(self, server: int, state: Dict):
		pass

	def get_global_state(self) -> Dict:
		pass

	def set_global_state(self, state: Dict):
		pass

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		pass

	async def on_message(self, bot: PluginAPI, metadata: util.MessageMetadata, message: discord.Message):
		pass

	async def on_mention(
			self,
			bot: PluginAPI,
			metadata: util.MessageMetadata,
			message: str,
			mentions: Sequence[util.Mention]
	):
		"""
		:param bot: The bot to interface with.
		:param metadata: The metadata from the message.
		:param message: The text of the message.
		:param mentions: The mentions, not necessarily in order.
		"""
		pass

	async def on_setting_change(self, bot: PluginAPI, key: str, old_value: Any, new_value: Any):
		pass

	async def on_regex_match(self, bot: PluginAPI, metadata: util.MessageMetadata, *match_groups: str):
		pass

	async def on_timer_fire(self, bot: PluginAPI):
		pass

	async def on_reaction(self, bot: PluginAPI, metadata: util.MessageMetadata, reaction: util.Reaction):
		pass

	def _create_resource_dirs(self, resource_path):
		path_dirs = []
		parent_dir = os.path.split(resource_path)[0]

		while parent_dir != '':
			parent_dir, cur_dir = os.path.split(parent_dir)
			path_dirs.insert(0, cur_dir)

		cur_create_dir = self._resource_dir
		for new_dir in path_dirs:
			cur_create_dir = os.path.join(cur_create_dir, new_dir)
			if not os.path.exists(cur_create_dir):
				os.mkdir(cur_create_dir)
