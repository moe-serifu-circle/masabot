from . import BotBehaviorModule, RegexTrigger, InvocationTrigger, MentionTrigger, mention_target_self
from ..util import BotSyntaxError
from .. import util
from .. import bot
import discord

import re
import logging
import random

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)

positive_words = [
	"thanks",
	"thank you",
	"good bot",
	"good girl",
	"good job",
	"thank",
]

negative_words = [
	"fuck you",
	"fuck off",
	"bad bot",
	"thanks for nothing",
	"broken",
]

positive_responses = [
	"Oh, thanks!",
	"Eheheh ^_^",
	"Do you really think so? :O",
	"I think you're pretty awesome too!",
	"I'm really glad!",
	"Um! I'm not sure I deserve that >///<",
	"W-well I'm not sure that's necessary, but, um, thanks!",
	"I'm so glad you think so!",
	"I'm always happy to help!",
	"Haiiiiiiiii!",
]

negative_responses = [
	"I'm sorry!",
	"Oh, oh no... I didn't mean to!",
	"Fuwawawaaaaaa @_@",
	":("
	"P-please, I didn't mean to be bad.",
	"Oh no oh no oh no! I'm really sorry!",
	"Oh.",
	"Did you have to do that?"
]


class NoticeMeSenpaiModule(BotBehaviorModule):

	def __init__(self, bot_api, resource_root):
		help_text = "The \"Notice me, Senpai\" module makes masabot react to messages that mention her."

		super().__init__(
			bot_api,
			name="noticeme",
			desc="Makes MasaBot react to mentions",
			help_text=help_text,
			triggers=[
				MentionTrigger(target=mention_target_self()),
				RegexTrigger(r'.*\b[Mm][Aa][Ss][Aa](?:[Bb][Oo][Tt])?\b.*')
			],
			resource_root=resource_root,
			has_state=False
		)

	async def on_regex_match(self, context, metadata, *match_groups):
		"""
		:type context: masabot.bot.BotContext
		:type metadata: masabot.util.MessageMetadata
		:type match_groups: str
		"""
		await self._handle_mention(context, match_groups[0])

	async def on_mention(self, context, metadata, message: discord.Message, mentions):
		await self._handle_mention(context, message.content)

	async def _handle_mention(self, context: bot.BotContext, message_text: str):
		sentiment = analyze_sentiment(message_text)
		if sentiment > 0:
			await self.bot_api.reply(context, random.choice(positive_responses))
		elif sentiment < 0:
			await self.bot_api.reply(context, random.choice(negative_responses))


def analyze_sentiment(message_text):
	"""
	Returns 1 for positive, 0 for neutral, -1 for negative.
	:param message_text:
	:return:
	"""
	all_words = {k.lower(): True for k in positive_words}
	all_words.update({k.lower(): False for k in negative_words})
	all_word_patterns = list(all_words.keys())
	all_word_patterns.sort()

	found = False
	positive = False
	for p in all_word_patterns:
		m = re.search(r"\b" + p + "\b", message_text, re.IGNORECASE | re.MULTILINE)
		if m:
			found = True
			positive = all_words[p]
			break
	if not found:
		return 0
	if positive:
		return 1
	return -1


BOT_MODULE_CLASS = NoticeMeSenpaiModule
