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
			self.assertEqual(actual, expected, msg="for " + repr(message_text) + "; expected " + ("no " if not expected else "") + "match but got " + ("no " if not actual else "") + "match")
