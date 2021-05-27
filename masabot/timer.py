import logging
import traceback
from typing import Coroutine, Optional

import asyncio

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class Timer(object):
	def __init__(self, action: Coroutine, period: int, id: Optional[str] = None):
		"""
		Creates a new timer for the given module.

		:param action: the action to perform on fire.
		:type period: int
		:param period: The number of seconds between fires of the timer.
		"""
		self.has_run = False
		self.next_run = 0
		self.future = None
		self.period = period
		self.id = id
		self._action = action

	def tick(self, now_time: float, on_fire_error) -> bool:
		"""
		Advances the timer by one tick and fires it asynchronously if it is ready to fire.

		:type now_time: float
		:param now_time: Monotonic current time.
		:type on_fire_error: (str) -> {__await__}
		:param on_fire_error: Accepts a message and properly reports it.

		:return: whether the tick resulted in a fire.
		"""

		fired_on_this_tick = False
		if not self.has_run or self.next_run <= now_time:
			# make any last tasks have finished before attempting to run again:
			if self.future is None or self.future.done():
				self.future = asyncio.ensure_future(self.fire(on_fire_error))
				self.has_run = True
				fired_on_this_tick = True
			if not self.has_run:
				self.next_run = now_time + self.period
			else:
				self.next_run = self.next_run + self.period

		return fired_on_this_tick

	async def fire(self, on_error):
		_log.debug("Firing timer " + repr(self.id))
		# noinspection PyBroadException
		try:
			await self._action
		except Exception:
			_log.exception("Encountered error in timer-triggered function")
			msg = "Exception in firing timer " + repr(self.id) + ":\n\n```python\n"
			msg += traceback.format_exc()
			msg += "\n```"
			await on_error
