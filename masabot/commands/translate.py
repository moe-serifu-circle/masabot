from . import BotBehaviorModule, InvocationTrigger
from ..util import BotSyntaxError, BotModuleError

import googletrans
import logging


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class TranslationModule(BotBehaviorModule):

	def __init__(self, bot_api, resource_root):
		help_text = "To translate text, type `tl` followed by the phrase to translate (in quotes):\n\n`tl"
		help_text += " \"안녕하세요\"`\n\nThe text will be translated to English, and the source language will be"
		help_text += " automatically detected.\n\nTo set the source language, give the code of the language after the"
		help_text += " text:\n\n`tl \"veritas lux mea\" la`\n\nTo give the source and the destination language, give"
		help_text += " the destination language after the source language:\n\n`tl \"안녕하세요\" ko ja`."

		super().__init__(
			bot_api,
			name="translate",
			desc="Translate text",
			help_text=help_text,
			triggers=[
				InvocationTrigger('tl'),
			],
			resource_root=resource_root,
			has_state=False
		)

		self._translator = googletrans.Translator()

		self._langs = {
			'af': 'afrikaans',
			'sq': 'albanian',
			'am': 'amharic',
			'ar': 'arabic',
			'hy': 'armenian',
			'az': 'azerbaijani',
			'eu': 'basque',
			'be': 'belarusian',
			'zh-CH': 'chinese',
			'hr': 'croatian',
			'da': 'danish',
			'nl': 'dutch',
			'en': 'english',
			'eo': 'esperanto',
			'tl': 'filipino',
			'fr': 'french',
			'de': 'german',
			'el': 'greek',
			'haw': 'hawaiian',
			'iw': 'hebrew',
			'ga': 'irish',
			'it': 'italian',
			'ja': 'japanese',
			'ko': 'korean',
			'lo': 'lao',
			'la': 'latin',
			'ms': 'malay',
			'pt': 'portuguese',
			'ru': 'russian',
			'es': 'spanish',
			'th': 'thai',
			'uk': 'ukranian',
			'vi': 'vietnamese',
			'ro': 'romanian'
		}

	async def on_invocation(self, context, metadata, command, *args):
		"""
		:type context: masabot.bot.BotContext
		:type metadata: masabot.util.MessageMetadata
		:type command: str
		:type args: str
		"""
		if len(args) < 1:
			raise BotSyntaxError("I don't know what you want me to translate...")

		source = None
		dest = 'en'
		text = args[0]

		if len(args) > 1:
			source = args[1]

		if len(args) > 2:
			dest = args[2]

		async with context.source.typing():
			try:
				if source is not None:
					trans = self._translator.translate(text, src=source, dest=dest)
				else:
					trans = self._translator.translate(text, dest=dest)
			except ValueError:
				raise BotSyntaxError("Your source or destination language was not valid!")

			msg = "Sure, I'll translate that"
			if source is None:
				if trans.src in self._langs:
					msg += "! I think it's in " + self._langs[trans.src].capitalize() + ", right?"
				else:
					msg += "! I think it's in " + trans.src + ", but I'm not sure what language that is!"
					msg += " But you can ask my operators to add it."
			else:
				msg += " from " + self._langs.get(source, source).capitalize() + "."

			msg += "\nIn " + self._langs.get(dest, dest).capitalize() + ", it would be:\n```\n"
			msg += trans.text + "\n```"

			if trans.pronunciation is not None and trans.pronunciation != trans.text:
				msg += "Oh, and the reading is:\n```\n" + trans.pronunciation + "\n```"

		await self.bot_api.reply(context, msg)


BOT_MODULE_CLASS = TranslationModule
