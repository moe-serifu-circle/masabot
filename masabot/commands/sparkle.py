from . import BotBehaviorModule, RegexTrigger, InvocationTrigger, ReactionTrigger
from ..util import BotSyntaxError
from .. import util, settings
from ..bot import PluginAPI

import logging
import random


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class SparkleModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "I got a new bottle of glitter that I like to carry around with me! Sometimes I'll put glitter on" \
					"things! ^_^ If this breaks, just type: '!settings sparkle enable false' to turn it off!\n\n"

		super().__init__(
			name="sparkle",
			desc= "I got a bottle of ✨glitter✨ and I collect it! Sometimes I put it on things!",
			help_text=help_text,
			triggers=[
				RegexTrigger('.*'),
				ReactionTrigger(emoji=['✨'])
			],
			resource_root=resource_root,
			has_state=True,
			server_only_settings=[
				settings.Key(settings.key_type_toggle, 'enable', default=False),
				settings.Key(settings.key_type_percent, 'start-chance', default=0.3),
				settings.Key(settings.key_type_percent, 'spread-chance', default=0.6),
				settings.Key(settings.key_type_int, 'spread-min', default=3),
				settings.Key(settings.key_type_int, 'spread-max', default=10),
				settings.Key(settings.key_type_percent, 'infect-chance', default=10),
				settings.Key(settings.key_type_percent, 'infect-by-post-chance', default=0.5),
				settings.Key(settings.key_type_int, 'infect-by-post-min', default=5),
				settings.Key(settings.key_type_int, 'infect-by-post-max', default=30),
				settings.Key(settings.key_type_int, 'infect-by-time-min', default=600),
				settings.Key(settings.key_type_int, 'infect-by-time-max', default=1200),
				settings.Key(settings.key_type_percent, 'opinion-chance', default=0.5),
				settings.Key(settings.key_type_percent, 'opinion-approval', default=0.7),
			]
		)

	async def on_regex_match(self, bot: PluginAPI, metadata: util.MessageMetadata, *match_groups: str):
		if not await bot.get_setting('enabled'):
			return

		chance = await bot.get_setting('start-chance')
		if random.random() < chance:
			await bot.react('✨')

	async def on_reaction(self, bot: PluginAPI, metadata: util.MessageMetadata, reaction: util.Reaction) -> bool:
		if not await bot.get_setting('enabled'):
			return False

		spread_chance = await bot.get_setting('spread-chance')
		if random.random() < spread_chance:
			await spread(bot)
		return False


async def spread(bot: PluginAPI):
	spread_min = await bot.get_setting('spread-min')
	spread_max = await bot.get_setting('spread-max')
	spread_amount = random.randint(spread_min, spread_max)
	msg_ids = await bot.get_messages()
	if len(msg_ids) < 1:
		return
	if spread_amount >= len(msg_ids):
		spread_amount = len(msg_ids) - 1
	for mid in msg_ids[1:spread_amount + 1]:
		await bot.react('✨', mid)
	await bot.reply(random.choice(
		"Oh no, glitter got EVERYWHERE!",
		"AHHH! You knocked over the glitter bottle!",
		"Achoooo! >.< Oh, I'm so sorry, glitter is everywhere!",
		"Wait wai- ohhhhh there was already a pile of glitter there...",
		"Ahahahahaha you have activated my trap card, pot of glitter, which allows me to throw it everywhere!",
		"Whoops! I accidentally ran too fast to see what you were reacting to and my RAM overflowed with glitter."
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
		"AHAOIUUDUAUHUAHAUHAU H i think i have a virus, it's fixed now, but- oh no, the glitter!",
	))




BOT_MODULE_CLASS = SparkleModule
