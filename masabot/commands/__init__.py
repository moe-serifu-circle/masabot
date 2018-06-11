__all__ = [
	'karma'
]


class BotModuleError(RuntimeError):
	def __init__(self, message):
		super().__init__(message)


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


class BotBehaviorModule(object):
	def __init__(self, bot_api, name, desc, help_text, triggers, has_state=False, requires_op=False):
		self.help_text = help_text
		self.description = desc
		self.name = name
		self.has_state = has_state
		self.triggers = triggers
		self.bot_api = bot_api
		self.requires_op = requires_op

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
