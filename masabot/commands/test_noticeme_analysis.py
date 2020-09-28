from unittest import TestCase
from . import noticeme_analysis as analysis


class TestNoticeMeAnalysis(TestCase):

	def test_contains_thanks(self):
		test_cases = [
			("thanks <@1234>", True),
			("<@1234> thanks", True),
			("<@1235> thanks", False),
			("thanks masabot", True),
			("masabot thanks", True),
			("masabot, thanks", True),
		]

		for case in test_cases:
			message_text, expected = case
			actual = analysis.contains_thanks(message_text, 1234, 'MasaBot')
			fmt = "for {!r}; expected {:s}match but got {:s}match"
			msg = fmt.format(message_text, "no " if not expected else "", "no " if not actual else "")
			self.assertEqual(actual, expected, msg=msg)
