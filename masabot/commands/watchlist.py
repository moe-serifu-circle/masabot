from . import BotBehaviorModule, InvocationTrigger
from ..util import BotModuleError, BotSyntaxError
from ..http import HttpAgent
from .. import util


import urllib.parse
import requests
import re
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
				InvocationTrigger("animelist"),
				InvocationTrigger("animelist-auth")
			],
			has_state=True
		)

		self._anilist_users = {}
		self._anilist_clients = {}
		""":type : dict[str, HttpAgent]"""
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
		if 'anilist-users' in state:
			self._anilist_users = state['anilist-users']
		for uid in self._anilist_users:
			self._anilist_clients[uid] = self._create_anilist_client(uid)

	def get_state(self):
		return {
			'anilist-users': self._anilist_users
		}

	async def on_invocation(self, context, command, *args):
		if command == "animelist-auth":
			if context.author.id not in self._anilist_users:
				await self.authorize(context)
			else:
				await self.bot_api.reply(context, "I already have an access token for you!")
		elif command == "animelist":
			await self._show_anilist(context, args)

	async def _show_anilist(self, context, args):
		uid = context.author.id
		if len(args) > 0:
			m = re.search(r'<@!?(\d+)>$', args[0], re.DOTALL)
			if m is None:
				msg = "I can only look up the anime lists of users, and " + repr(str(args[0])) + " is not a user!"
				raise BotSyntaxError(msg)
			uid = m.group(1)
		await self.bot_api.reply_typing(context)
		anime_list = self.get_user_anime_list(uid)
		pager = util.DiscordPager()
		pager.add_line("Okay! Here is <@!" + context.author.id + ">'s Anilist:")
		pager.add_line()
		self.format_anime_list(anime_list, pager)
		for page in pager.get_pages():
			await self.bot_api.reply(context, page)

	# noinspection PyMethodMayBeStatic
	def format_anime_list(self, anime_list, pager):
		sorted_by_status = {
			'CURRENT': [],
			'PLANNING': [],
			'COMPLETED': [],
			'DROPPED': [],
			'PAUSED': [],
			'REPEATING': []
		}

		for anime in anime_list:
			sorted_by_status[anime['status']].append(anime)

		def format_eps(anime_list, heading, show_eps, pager):
			if len(anime_list) > 0:
				pager.add_line(heading + ":")
				pager.start_code_block()
				for anime in anime_list:
					list_item = '* "'
					titles = anime['media']['title']
					if titles['english'] is not None:
						list_item += titles['english']
					elif titles['romaji'] is not None:
						list_item += titles['romaji']
					else:
						list_item += titles['native']
					list_item += '"'
					if show_eps:
						list_item += ' (' + str(anime['progress']) + "/" + str(anime['media']['episodes']) + " episodes)"
					pager.add_line(list_item)
				pager.end_code_block()

		format_eps(sorted_by_status['CURRENT'], "Current Anime", True, pager)
		format_eps(sorted_by_status['REPEATING'], "Repeating", True, pager)
		format_eps(sorted_by_status['COMPLETED'], "Completed", False, pager)
		format_eps(sorted_by_status['PAUSED'], "On-hold", True, pager)
		format_eps(sorted_by_status['DROPPED'], "Dropped", True, pager)
		format_eps(sorted_by_status['PLANNING'], "Plan-to-watch", False, pager)

		return pager

	def get_user_anime_list(self, uid, include_private=False):
		self._require_auth(uid)

		gql = (
			"query GetAnimeList($uid: Int, $page: Int, $sort: [MediaListSort]) {"
			"	Page(page: $page, perPage: 50) {"
			"		pageInfo {"
			"			total"
			"			currentPage"
			"			lastPage"
			"			hasNextPage"
			"			perPage"
			"		}"
			"		mediaList(userId: $uid, type: ANIME, sort: $sort) {"
			"			status"
			"			score"
			"			progress"
			"			private"
			"			startedAt {"
			"				year"
			"				month"
			"				day"
			"			}"
			"			completedAt {"
			"				year"
			"				month"
			"				day"
			"			}"
			"			media {"
			"				episodes"
			"				title {"
			"					english"
			"					romaji"
			"					native"
			"					userPreferred"
			"				}"
			"				isAdult"
			"			}"
			"		}"
			"	}"
			"}"
		)

		full_list = []
		page = 1
		cl = self._anilist_clients[uid]
		while True:
			payload = {
				'query': gql,
				'variables': {
					"uid": self._anilist_users[uid]['id'],
					"page": page
				}
			}
			_, resp = cl.request('POST', '/', payload=payload, auth=True)
			page_list = resp['data']['Page']['mediaList']
			full_list += [x for x in page_list if x['private'] == include_private]
			page_info = resp["data"]["Page"]["pageInfo"]
			if page_info['currentPage'] == page_info['lastPage']:
				break
			else:
				page += 1

		return full_list

	async def authorize(self, context):
		auth_payload = {
			'client_id': self._anilist_id,
			'redirect_uri': "https://github.com/moe-serifu-circle/masabot/blob/master/docs/oauth2-authorization-code.md",
			'response_type': 'code'
		}

		p = requests.Request('GET', 'https://anilist.co/api/v2/oauth/authorize', params=auth_payload).prepare()

		msg = "Oh! You want to authorize me to use your Anilist profile? Okay! I need you go to this website"
		msg += " and tell Anilist that it's okay for me to access your profile first, okay?\n\nWhen you finish at that"
		msg += " website, tell me what the authorization code is and then I'll be able to continue!\n\n" + p.url

		await self.bot_api.reply(context, msg)

		code_url = await self.bot_api.prompt(context, "What's the authorization code?")
		if code_url is None:
			msg = "I really need you to access that website and tell me what the code is if you want to use Anilist!"
			msg += " Let me know if you want to try again sometime, okay?"
			raise BotModuleError(msg)

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

		await self.bot_api.reply_typing(context)
		_log.debug("Sending token request to Anilist...")
		resp = requests.post('https://anilist.co/api/v2/oauth/token', data=token_payload)
		_log.debug("Response from Anilist: " + repr(resp.text))
		try:
			resp_json = resp.json()
		except json.decoder.JSONDecodeError:
			msg = "Oh no! There was a problem with that request! Anilist told me:\n```\n" + resp.text + "\n```"
			raise BotModuleError(msg)

		# TODO: actually use the 'expires-in' response object
		if 'access_token' in resp_json:
			self._anilist_users[context.author.id] = {
				'token': resp_json['access_token']
			}
			self._anilist_clients[context.author.id] = self._create_anilist_client(context.author.id)
			_log.debug("User " + context.author.id + " is now authenticated to use Anilist")
			_log.debug("Getting Anilist UID...")
			_, user_data = self._anilist_clients[context.author.id].request('POST', '/', auth=True, payload={
				'query': "{Viewer{id}}"
			})
			anilist_id = user_data['data']['Viewer']['id']
			_log.debug("Got back UID: " + str(anilist_id))

			self._anilist_users[context.author.id]['id'] = anilist_id
			await self.bot_api.reply(context, "Hooray! Now you can use my Anilist functionality!")
		else:
			msg = "There was a problem when I tried to use that authorization code! Maybe we can try again in a"
			msg += " bit?"
			raise BotModuleError(msg)

	def _create_anilist_client(self, uid):
		def auth_func(req):
			req.headers['Authorization'] = 'Bearer ' + self._anilist_users[uid]['token']
			return req.prepare()

		client = HttpAgent("graphql.anilist.co", ssl=True, auth_func=auth_func)

		return client

	def _require_auth(self, uid):
		if uid not in self._anilist_users:
			msg = "I haven't been given permission to access <@!" + uid + ">'s Anilist profile yet! But they can"
			msg += " authorize me with the `animelist-auth` command."
			raise BotModuleError(msg)


BOT_MODULE_CLASS = WatchListModule
