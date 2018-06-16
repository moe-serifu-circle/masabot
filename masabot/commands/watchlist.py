from . import BotBehaviorModule, RegexTrigger, InvocationTrigger
from ..bot import BotModuleError

import requests
import logging


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class WatchListModule(BotBehaviorModule):

	def __init__(self, bot_api):
		help_text = ""

		super().__init__(
			bot_api,
			name="watchlist",
			desc="Manages list of current anime on Anilist",
			help_text=help_text,
			triggers=[
				InvocationTrigger("animelist")
			],
			has_state=True
		)

		self._anilist_oauth_tokens = {}
		self._anilist_secret = ""
		self._anilist_id = ""

	def load_config(self, config):
		if 'anilist-client-id' not in config:
			raise BotModuleError("Watchlist module requires the Anilist client ID")
		if 'anilist-client-secret' not in config:
			raise BotModuleError("Watchlist module requires the Anilist client secret")
		self._anilist_secret = config['anilist-client-secret']
		self._anilist_id = config['anilist-client-id']

	def set_state(self, state):
		if 'anilist-oauth-tokens' in state:
			self._anilist_oauth_tokens = state['anilist-oauth-tokens']

	def get_state(self):
		return {
			'anilist-oauth-tokens': self._anilist_oauth_tokens
		}

	async def on_invocation(self, context, command, *args):
		if context.author.id not in self._anilist_oauth_tokens:
			await self.authorize(context)

	async def authorize(self, context):
		auth_payload = {
			'client_id': self._anilist_id,
			'redirect_uri': "https://github.com/moe-serifu-circle/masabot/elsewhere",
			'response_type': 'code'
		}

		p = requests.Request('GET', 'https://anilist.co/api/v2/oauth/authorize', params=auth_payload).prepare()

		msg = "Oh! It looks like you've never used my Anilist functionality before. I need you go to this website"
		msg += " and tell Anilist that it's okay for me to access your profile first, okay?\n\nWhen you finish at that"
		msg += " website, tell me what the authorization code is and then I'll be able to continue!\n\n" + p.url

		await self.bot_api.reply(context, msg)

		code = await self.bot_api.prompt(context, "What's the authorization code?")
		if code is None:
			raise BotModuleError("Oauth flow interrupted")


BOT_MODULE_CLASS = WatchListModule
