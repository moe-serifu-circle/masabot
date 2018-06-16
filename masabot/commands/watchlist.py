from . import BotBehaviorModule, RegexTrigger, InvocationTrigger
from ..bot import BotModuleError


import urllib.parse
import requests
import logging
import json.decoder


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
		else:
			await self.bot_api.reply(context, "I already have an access token for you!")

	async def authorize(self, context):
		auth_payload = {
			'client_id': self._anilist_id,
			'redirect_uri': "https://github.com/moe-serifu-circle/masabot/blob/master/docs/oauth2-authorization-code.md",
			'response_type': 'code'
		}

		p = requests.Request('GET', 'https://anilist.co/api/v2/oauth/authorize', params=auth_payload).prepare()

		msg = "Oh! It looks like you've never used my Anilist functionality before. I need you go to this website"
		msg += " and tell Anilist that it's okay for me to access your profile first, okay?\n\nWhen you finish at that"
		msg += " website, tell me what the authorization code is and then I'll be able to continue!\n\n" + p.url

		await self.bot_api.reply(context, msg)

		code_url = await self.bot_api.prompt(context, "What's the authorization code?")
		if code_url is None:
			raise BotModuleError("Oauth flow interrupted")

		parsed_url = urllib.parse.urlparse(code_url)
		query = urllib.parse.parse_qs(parsed_url.query)
		if not 'code' in query:
			raise BotModuleError("That URL doesn't contain a valid authorization code in it!")
		code = query['code']

		token_payload = {
			'grant_type': 'authorization_code',
			'client_id': self._anilist_id,
			'client_secret': self._anilist_secret,
			'redirect_uri': "https://github.com/moe-serifu-circle/masabot/blob/master/docs/oauth2-authorization-code.md",
			'code': code
		}

		_log.debug("Sending token request to Anilist...")
		resp = requests.post('https://anilist.co/api/v2/oauth/token', data=token_payload)
		_log.debug("Response from Anilist: " + repr(resp.text))
		try:
			resp_json = resp.json()
		except json.decoder.JSONDecodeError:
			msg = "Oh no! There was a problem with that request! Anilist told me:\n```\n" + resp.text + "\n```"
			raise BotModuleError(msg)

		if 'access_token' in resp_json:
			self._anilist_oauth_tokens[context.author.id] = resp_json['access_token']
			_log.debug("User " + context.author.id + " is now authenticated to use Anilist")

			await self.bot_api.reply(context, "Hooray! Now you can use my Anilist functionality!")
		else:
			msg = "There was a problem when I tried to use that authorization code! Maybe we can try again in a"
			msg += " bit?"
			raise BotModuleError(msg)


BOT_MODULE_CLASS = WatchListModule
