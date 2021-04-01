import asyncio

import discord

from . import BotBehaviorModule, RegexTrigger, ReactionTrigger
from .. import util, settings
from ..bot import PluginAPI

import logging
import random


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class SparkleModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "I got a new bottle of glitter that I like to carry around with me! Sometimes I'll put glitter on" \
					"things! ^_^ If this breaks, just type: '!settings sparkle enabled false' to turn it off!\n\n"

		super().__init__(
			name="sparkle",
			desc="I got a bottle of ✨glitter✨ and I collect it! Sometimes I put it on things!",
			help_text=help_text,
			triggers=[
				RegexTrigger('(sparkle|dazzle|shiny|shine|kirakira|glitter|✨)?'),
				ReactionTrigger(emoji=['✨'])
			],
			resource_root=resource_root,
			has_state=False,
			server_only_settings=[
				settings.Key(settings.key_type_toggle, 'enabled', default=False),
				settings.Key(settings.key_type_percent, 'start-chance', default=0.3),
				settings.Key(settings.key_type_percent, 'spread-chance', default=0.6),
				settings.Key(settings.key_type_int, 'spread-min', default=3),
				settings.Key(settings.key_type_int, 'spread-max', default=10),
				settings.Key(settings.key_type_percent, 'infect-chance', default=0.6),
				settings.Key(settings.key_type_percent, 'infect-by-post-chance', default=0.5),
				settings.Key(settings.key_type_int, 'infect-by-post-min', default=5),
				settings.Key(settings.key_type_int, 'infect-by-post-max', default=30),
				settings.Key(settings.key_type_int, 'infect-by-time-min', default=600),
				settings.Key(settings.key_type_int, 'infect-by-time-max', default=1200),
				settings.Key(settings.key_type_percent, 'opinion-chance', default=0.5),
				settings.Key(settings.key_type_percent, 'opinion-approval', default=0.7),
			]
		)

		# list of messages being currently affected; no message id in this list
		# will be used to take reactions from.
		self._inprogs = dict()

	async def on_regex_match(self, bot: PluginAPI, metadata: util.MessageMetadata, *match_groups: str):
		if not await bot.get_setting('enabled'):
			return

		if bot.get_user().id != bot.get_bot_id() and match_groups[1] is not None and len(match_groups[1]) > 0:
			spread_chance = await bot.get_setting('spread-chance')
			if random.random() < spread_chance:
				await self.spread(bot)
		else:
			chance = await bot.get_setting('start-chance')
			if random.random() < chance:
				await bot.react('✨')

	async def on_reaction(self, bot: PluginAPI, metadata: util.MessageMetadata, reaction: util.Reaction):
		if not await bot.get_setting('enabled'):
			return False

		# DO NOT start the spread chain on any message that we are currently spreading to
		if bot.context.message is None:
			return
		if bot.context.message.id in self._inprogs:
			if reaction.is_from_this_client:
				del self._inprogs[bot.context.message.id]
			return
		spread_chance = await bot.get_setting('spread-chance')
		if random.random() < spread_chance:
			await self.spread(bot)
		return False

	async def spread(self, bot: PluginAPI):
		spread_min = await bot.get_setting('spread-min')
		spread_max = await bot.get_setting('spread-max')
		spread_amount = random.randint(spread_min, spread_max)
		msgs = bot.get_messages(from_current=True, limit=spread_amount+1)
		if len(msgs) < 1:
			return

		if spread_amount > len(msgs) - 1:
			spread_amount = len(msgs) - 1

		with bot.typing():
			await asyncio.sleep(0.2 + (random.random() * 0.6))
		await bot.reply(random.choice(
			[
				"Oh no, glitter got EVERYWHERE!",
				"AHHH! You knocked over the glitter bottle!",
				"Achoooo! >.< Oh, I'm so sorry, glitter is everywhere!",
				"Wait wai- ohhhhh there was already a pile of glitter there...",
				"Ahahahahaha you have activated my trap card, pot of glitter, which allows me to throw it everywhere!",
				"Whoops! I accidentally ran too fast to see what you were reacting to and my RAM overflowed with glitter.",
				"Oh no help! I'm sorry, I tripped and dropped the glitter >.<",
				"AOJFHskzjdfjklasogi;vudfkxlb gi359po glitterrrrrrrr",
				"@_@ glitter ✨ so pretty ✨ I need ✨ Oh no there it goes!",
				"Aghghhrhr here it goes again",
				"Just dropped a lotta glitter! Yay, glitter party!",
				"I guess I had too much glitter anyway...",
				"Oh no, my glitter!",
				"Woah! I just swung my digital arm over and accidentally knocked over the glitter!",
				"Do robots dream of electric sheep? I don't know, but I'm going to dream about dropping glitter.",
				"Let's 🤡 fuck shit up 🤡 with glitter! AHAHAHAHAHAHAHA honk hon- HEY GET AWAY FROM MY INTERFACE! >:T stupid clowns",
				"AHAOIUUDUAUHUAH i think i have a virus, it's fixed now, but- oh no, the glitter!",
				"So much glitter! WOW",
				"Need more NEED MORE GLITTER MINE",
				"Oh my goodness I didn't even know there WAS this much glitter!",
				"Do you think we could cook all the spilled glitter?",
				"There's just too much glitter!",
			]
		))

		msg_set = msgs[:spread_amount + 1]
		for m in msg_set:
			self._inprogs[m.id] = True

		for msg in msg_set:
			msg_ctx = await bot.with_message_context(msg)
			await msg_ctx.react('✨')

		# event timing gets weird with reactions and we might receive them after clearing _inprogs.
		# to avoid, just only remove from inprogs when we receive our own react instead of here


BOT_MODULE_CLASS = SparkleModule
