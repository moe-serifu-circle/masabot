from . import BotBehaviorModule, RegexTrigger, InvocationTrigger, MentionTrigger, mention_target_self
from ..util import BotSyntaxError
from .. import util
from .. import bot
import discord

import logging
import random

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


positive_responses = [
	"Oh, thanks!",
	"Eheheh ^_^",
	"Do you really think so? :O",
	"I think you're pretty awesome too!",
	"I'm really glad!",
	"Um! I'm not sure I deserve that >///<",
	"W-well I'm not sure that's necessary, but, um, thanks!",
	"I'm so glad you think so!",
	"I'm happy to help!",
	"Haiiiiiiiii!"
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
		if sentiment_is_good(message_text):
			await self.bot_api.reply(context, "")


def analyze_sentiment(message_text):


BOT_MODULE_CLASS = NoticeMeSenpaiModule
