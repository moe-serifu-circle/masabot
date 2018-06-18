import datetime

__all__ = [
	'karma',
	'animeme',
	'translate',
	'roll',
	'animelist'
]


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
	def __init__(self, bot_api, name, desc, help_text, triggers, has_state=False):
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
