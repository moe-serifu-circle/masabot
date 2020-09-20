import asyncio
from typing import Dict

from . import BotBehaviorModule, RegexTrigger, MentionTrigger, InvocationTrigger, mention_target_self, noticeme_analysis
from .. import settings, util
from ..bot import PluginAPI

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
	"I'm always happy to help!",
	"Haiiiiiiiii!",
]

negative_responses = [
	"I'm sorry!",
	"Oh, oh no... I didn't mean to be a bother :c",
	"Fuwawawaaaaaa @_@",
	":("
	"P-please, I didn't mean to be bad.",
	"Oh no oh no oh no! I'm really sorry!",
	"Oh.",
	"Did you have to do that?"
]

positive_thanks_responses = [
	"Of course!",
	"You're very welcome, I'm glad I could help!",
	"A good bot does what she can to help out!",
	"You don't have to thank me!",
	"I'm just happy to help make you happy!"
]

neutral_mention_reactions = [
	"👋",
	"👀",
	"❗",
	"😀",
	"❤️",
]


class NoticeMeSenpaiModule(BotBehaviorModule):
	def __init__(self, resource_root: str):
		help_text = "The \"Notice me, Senpai\" module makes me react to messages that mention me. It can be configured"
		help_text += " with the `noticeme-settings` command!"

		super().__init__(
			name="noticeme",
			desc="Makes MasaBot react to mentions",
			help_text=help_text,
			triggers=[
				MentionTrigger(target=mention_target_self()),
				RegexTrigger(r'.*\b[Mm][Aa][Ss][Aa](?:[Bb][Oo][Tt])?\b.*'),
				InvocationTrigger("noticeme-settings")

			],
			resource_root=resource_root,
			has_state=True
		)

		# TODO: standardize _settings in this fashion across all that use settings.
		self._settings = settings.SettingsStore()
		self._settings.create_percent_key('neutral_reaction_chance', 0.6)
		self._settings.create_int_key('min_reaction_delay_ms', 1000)
		self._settings.create_int_key('max_reaction_delay_ms', 7000)

	def set_state(self, server: int, state: Dict):
		self._settings.set_state(server, state)

	def get_state(self, server: int) -> Dict:
		return self._settings.get_state(server)

	def get_global_state(self) -> Dict:
		return self._settings.get_global_state()

	def set_global_state(self, state: Dict):
		self._settings.set_global_state(state)

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command, *args):
		reply = await bot.context.execute_setting_command(bot._bot, self._settings, args, module_name=self.name)
		for page in reply.get_pages():
			await bot.reply(page)

	async def on_regex_match(self, bot: PluginAPI, metadata: util.MessageMetadata, *match_groups: str):
		await self._handle_mention(bot, match_groups[0])

	async def on_mention(self, bot: PluginAPI, metadata, message: str, mentions):
		await self._handle_mention(bot, message)

	async def _handle_mention(self, bot: PluginAPI, message_text: str):
		analysis_chunks = message_to_analyzable_chunks(message_text)
		if len(analysis_chunks) < 1:
			return
		worst_sentiment = None
		neutral_present = False
		for message_text in analysis_chunks:
			sentiment = noticeme_analysis.analyze_sentiment(message_text)
			if sentiment == 0:
				neutral_present = True
				continue  # neutrals are checked next if no other is found
			if worst_sentiment is None:
				worst_sentiment = sentiment
			elif sentiment < worst_sentiment:
				worst_sentiment = sentiment
		if worst_sentiment is not None:
			_log.debug("got a mention; sentiment score is {:d}".format(worst_sentiment))
			if worst_sentiment > 0:
				if noticeme_analysis.contains_thanks(
						message_text, bot.get_bot_id(), "masabot", "masa", "masachan", "masa-chan"):
					reply_text = random.choice(positive_thanks_responses)
				else:
					reply_text = random.choice(positive_responses)
				await bot.reply(reply_text)
			elif worst_sentiment < 0:
				await bot.reply(random.choice(negative_responses))
		elif neutral_present:
			if random.random() < bot.context.get_setting(self._settings, 'neutral_reaction_chance'):
				emoji_text = random.choice(neutral_mention_reactions)
				min_reaction_delay_ms = bot.context.get_setting(self._settings, 'min_reaction_delay_ms')
				max_reaction_delay_ms = bot.context.get_setting(self._settings, 'max_reaction_delay_ms')
				# give a slight delay
				delay = min_reaction_delay_ms + (random.random() * (max_reaction_delay_ms - min_reaction_delay_ms))  # random amount from min to max ms
				await asyncio.sleep((delay / 1000))
				await bot.react(emoji_text)


def message_to_analyzable_chunks(text: str):
	chunks = []
	paras = text.split('\n')
	for p in paras:
		sents = p.split('.')
		candidate = None
		has_more_than_one = False
		for s in sents:
			if s.strip(" \t\n\r\v") != "":
				if candidate is None:
					candidate = s
				else:
					has_more_than_one = True
					break
		if not has_more_than_one and candidate is not None:
			chunks.append(candidate)
	return chunks


BOT_MODULE_CLASS = NoticeMeSenpaiModule
