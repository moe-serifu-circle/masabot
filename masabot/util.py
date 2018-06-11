
def get_uid_from_mention(mention_text):
	"""
	:type mention_text: str
	"""
	"<@!?(\d+)>"
	mention_text = mention_text.strip()
	if not mention_text.startswith('<@') or not mention_text.endswith('>'):
		raise ValueError("Not a mention: '" + mention_text + "'")
	mention_text = mention_text[2:-1]
	if mention_text.startswith('!'):
		mention_text = mention_text[1:]
	return str(int(mention_text))
