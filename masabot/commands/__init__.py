import datetime
import os.path
import logging

__all__ = [
	'karma',
	'animeme',
	'translate',
	'roll',
	'animelist'
]



_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


def mention_target_any():
	return {'target_type': 'any'}


def mention_target_specific(*names):
	return {'target_type': 'specific', 'names': names}


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
	def __init__(self, days=0, seconds=0, minutes=0, hours=0, weeks=0):
		self.trigger_type = 'TIMER'
		self.timer_duration = datetime.timedelta(days=days, seconds=seconds, minutes=minutes, hours=hours, weeks=weeks)


class BotBehaviorModule(object):
	def __init__(self, bot_api, name, desc, help_text, triggers, resource_root, has_state=False):
		"""
		Create a new BotBehaviorModule instance.

		:type bot_api: masabot.bot.MasaBot
		:param bot_api: The interface back to the bot that is executing the module.
		:type name: str
		:param name: The name of the module. Must be unique among all loaded modules.
		:type desc: str
		:param desc: A brief description of what the command does. Should fit on a single line. This is displayed next
		to the command when `help` lists all modules.
		:type help_text: str
		:param help_text: A full help text including all information on the command. This is shown when the help for
		this particular module is displayed.
		:type triggers: list[InvocationTrigger | RegexTrigger | MentionTrigger | TimerTrigger]
		:param triggers: All possible triggers that cause this module to be executed.
		:type resource_root: str
		:param resource_root: The root directory that resources are to be placed in.
		:type has_state: bool
		:param has_state: Whether this module has state. If this is true, then the module should define get_state()
		set_state() methods for saving state to a dict and setting state from a dict.
		"""
		self.help_text = help_text
		self.description = desc
		self.name = name
		self.has_state = has_state
		self.triggers = triggers
		self.bot_api = bot_api
		self._resource_dir = os.path.join(resource_root, name)
		if not os.path.exists(self._resource_dir):
			os.mkdir(self._resource_dir)

	def open_resource(self, *resource_components, **kwargs):
		"""
		Open a resource in binary mode and get the file pointer for it. All resources are opened in binary mode; if text
		mode is needed, module state should be used instead.

		:type resource_components: str
		:param resource: The path to the resource to open. Must be relative to the resource store root for the module.
		:type for_writing: bool
		:param for_writing: Whether to open the resource for writing instead. Defaults to False.
		:type append: bool
		:param append: If opening the resource for writing, this sets whether to append to the end of the resource.
		Defaults to False.
		:rtype: File-like object.
		:return: The file like object ready for use.
		"""

		for_writing = kwargs.get('for_writing', False)
		append = kwargs.get('append', False)

		if resource_components[-1].endswith('/'):
			raise ValueError("Resource cannot end in a '/'")

		path = os.path.join(self._resource_dir, *resource_components)
		if for_writing:
			path_dirs = []
			parent_dir = resource_components[:-1]

			_log.info(parent_dir)
			while parent_dir != '':
				parent_dir, cur_dir = parent_dir[:-1], parent_dir[-1]
				path_dirs.insert(0, cur_dir)

			cur_create_dir = self._resource_dir
			for new_dir in path_dirs:
				cur_create_dir = os.path.join(cur_create_dir, new_dir)
				if not os.path.exists(cur_create_dir):
					os.mkdir(cur_create_dir)

			mode = 'wb'
			if append:
				mode += '+'
		else:
			mode = 'rb'

		return open(path, mode)

	def load_config(self, config):
		pass

	def get_state(self):
		pass

	def set_state(self, state):
		pass

	async def on_invocation(self, context, command, *args):
		pass

	async def on_mention(self, context, message, mention_names):
		pass

	async def on_regex_match(self, context, *match_groups):
		pass

	async def on_timer_fire(self):
		pass
