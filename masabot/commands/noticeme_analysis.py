import re
import logging
_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


positive_words = [
	"thanks",
	"thank you",
	"good bot",
	"good girl",
	"good job",
	"thank",
	"love you",
	"loves you",
]

negative_words = [
	"fuck you",
	"fuk off",
	"fuck off",
	"bad bot",
	"thanks for nothing",
	"broken",
]


def pattern_for_mention(uid: int, name: str) -> str:
	patt = r"(?:<@!?" + str(uid) + r">|"
	for ch in name:
		patt += "[" + re.escape(ch.lower()) + re.escape(ch.upper()) + "]"
	patt += ")"
	return patt


def contains_thanks(text: str, to_user_id: int, to_user_name: str) -> bool:
	thank_you_pattern = r"(?:thank|thanks|thank\s+you|thx)"
	mention_pattern = pattern_for_mention(to_user_id, to_user_name)
	left_pattern = re.compile(thank_you_pattern + r"[\s,]+" + mention_pattern, re.IGNORECASE)
	right_pattern = re.compile(mention_pattern + r"[\s,]+" + thank_you_pattern, re.IGNORECASE)

	if left_pattern.search(text):
		return True
	if right_pattern.search(text):
		return True
	return False


def analyze_sentiment(message_text):
	"""
	Returns 1 for positive, 0 for neutral, -1 for negative.
	:param message_text:
	:return:
	"""
	all_words = {k.lower(): True for k in positive_words}
	all_words.update({k.lower(): False for k in negative_words})
	all_word_patterns = list(all_words.keys())
	all_word_patterns.sort()

	found = False
	positive = False
	for p in all_word_patterns:
		m = re.search(r"\b" + p + r"\b", message_text, re.IGNORECASE | re.MULTILINE)
		if m:
			found = True
			positive = all_words[p]
			break
	if not found:
		return 0
	if positive:
		return 1
	return -1

