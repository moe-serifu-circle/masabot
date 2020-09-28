import asyncio

from . import BotBehaviorModule, RegexTrigger, MentionTrigger, mention_target_self, noticeme_analysis
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
			],
			resource_root=resource_root,
			settings=[
				settings.Key(settings.key_type_percent, 'neutral_reaction_chance', default=0.6),
				settings.Key(settings.key_type_int, 'min_reaction_delay_ms', default=1000),
				settings.Key(settings.key_type_int, 'max_reaction_delay_ms', default=7000),
			]
		)

	async def on_regex_match(self, bot: PluginAPI, metadata: util.MessageMetadata, *match_groups: str):
		await self._handle_mention(bot, match_groups[0])

	async def on_mention(self, bot: PluginAPI, metadata, message: str, mentions):
		await self._handle_mention(bot, message)

	# noinspection PyMethodMayBeStatic
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
			if random.random() < await bot.get_setting('neutral_reaction_chance'):
				emoji_text = random.choice(neutral_mention_reactions)
				min_reaction_delay_ms = await bot.get_setting('min_reaction_delay_ms')
				max_reaction_delay_ms = await bot.get_setting('max_reaction_delay_ms')
				# give a slight delay
				# random amount from min to max ms
				delay = min_reaction_delay_ms + (random.random() * (max_reaction_delay_ms - min_reaction_delay_ms))
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
