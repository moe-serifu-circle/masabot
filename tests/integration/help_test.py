from masabot.testerbot import BotCommandExecutor
import unittest
import os
import subprocess
import time

class HelpTest(unittest.TestCase):

	def setUp(self):
		api_key = os.environ['BOTCOMMAND_API_KEY']
		channel = os.environ['BOTCOMMAND_CHANNEL']
		target = os.environ['BOTCOMMAND_TARGET']
		self.command_executor = BotCommandExecutor(api_key, channel, target)
		self.command_executor.start()

	def test_run_help(self):
		self.command_executor.send_command("!help")
		out = self.command_executor.get_output()
		self.assertTrue(out.startswith("Sure! I'll tell you how to use my interface!"))

	def tearDown(self):
		self.command_executor.stop(10)
