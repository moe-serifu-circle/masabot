"""
Functions for working with HTTP and connections.
"""

# noinspection PyPackageRequirements
import requests
import pickle
import concurrent.futures
import logging
import time
import decimal


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


_default_http_headers = {
	"User-Agent": 'Mozilla/5.0',
	"Accept-Encoding": "deflate,gzip,identity"
}


def _log_http_request(req, uri, host, auth, full):
	query_text = ''
	if full and '?' in req.path_url:
		query_text = '?' + req.path_url.split('?', 1)[1]
	auth_text = "authenticated " if auth else ""
	_log.debug("Sending " + auth_text + "HTTP " + req.method.upper() + " " + uri + query_text + " to " + host)
	if full:
		_log.debug("Headers: " + str(req.headers))
		_log.debug("Body: " + str(req.body))


def _log_http_response(resp, full):
	_log.debug("Received response: HTTP " + str(resp.status_code))
	if full:
		_log.debug("Headers: " + str(resp.headers))
		_log.debug("Body: " + str(resp.content))


class AsyncHTTPError(Exception):
	"""
	Raised when at least one of the HTTP requests in an asynchronous group fails.
	"""
	def __init__(self, failed):
		"""
		Creates a new AsyncHTTPError.
		:param failed: The indexes of the requests that failed.
		"""
		super().__init__("One or more asynchronous HTTP requests failed: " + failed)
		self.failed = failed


class HttpAgent(object):
	"""
	Stateful HTTP client for talking to HTTP servers.
	"""

	def __init__(
			self,
			host,
			request_payload='json',
			response_payload='json',
			ignored_errors=None,
			ssl=False,
			log_full_request=True,
			log_full_response=True,
			auth_func=lambda x: x.prepare()
	):
		"""
		Create a new client.
		:type host: ``str``
		:param host: The hostname to use. Do not include the scheme at the beginning.
		:type request_payload: ``str``
		:param request_payload: How to encode the payload in requests when no option is given. Valid options
		are 'json' to send payload as 'application/json', or 'form' to send payload as
		'application/x-www-form-urlencoded'. Regardless of the choice here, it can be overridden per individual request.
		:type response_payload: ``str``
		:param response_payload: How to decode the payload in responses when no option is given. Valid options
		are 'json' to decode response payload as 'application/json' and return the interpreted map, 'text' to decode the
		content as characters, or 'binary' to do no encoding.
		Regardless of the choice here, it can be overridden per individual request.
		:type ignored_errors: ``list[int]``
		:param ignored_errors: A list of HTTP codes which should be ignored when checking for exceptions. Normally,
		HTTP responses that include codes in the 4XX or 5XX will cause an exception to be raised. Pass in a list of ints
		to give the specific codes that should not cause an error to be raised.
		:type ssl: ``bool``
		:param ssl: Whether SSL/TLS should be assumed to be the method of connecting for all requests, unless
		otherwise stated.
		:type log_full_request: ``bool``
		:param log_full_request: Whether to log an entire HTTP request (including all headers and body). If False, only
		the host and method will be logged. If True, the entire response will be logged, including body and headers in
		plaintext.
		:type log_full_response: ``bool``
		:param log_full_response: Whether to log an entire HTTP response (including all headers and body). If False,
		only the host and response code will be logged. If True, the entire response will be logged, including body and
		headers in plaintext.
		:type auth_func: ``(requests.Request) -> requests.PreparedRequest``
		:param auth_func: Adds authentication info to a request. Should not be used for plain HTML form authorization,
		but rather for methods inherent to HTTP, e.g. basic auth, bearer tokens, or signed digest.
		"""
		self._host = host.rstrip('/')
		if request_payload != 'json' and request_payload != 'form':
			raise ValueError("request_payload must be one of 'json' or 'form'.")
		if response_payload != 'text' and response_payload != 'json' and response_payload != 'binary':
			raise ValueError("response_payload must be one of 'json', 'text', or 'binary'.")
		self._default_request_payload = request_payload
		self._default_response_payload = response_payload
		self._ignored_http_errors = [] if ignored_errors is None else ignored_errors
		self._use_ssl = ssl
		self._session = None
		""":type : Optional[requests.Session]"""
		self._async_http_requests = []
		self._async_executor = concurrent.futures.ThreadPoolExecutor(max_workers=100)
		self._async_transforms = []
		self._auth_func = auth_func
		self._log_full_request = log_full_request
		self._log_full_response = log_full_response

	def start_new_session(self):
		if self._session is not None:
			self._session.close()
		self._session = requests.Session()
		self._session.headers.update(_default_http_headers)

	def add_async_request(
			self,
			method,
			uri,
			host=None,
			query=None,
			payload=None,
			auth=False,
			after=lambda x: x,
			**kwargs
	):
		"""
		Adds an HTTP request to be ansynchronously started. The request is not fired until send_asyncs() is
		called.
		:type method: ``str``
		:param method: The HTTP method to use for requesting. Usually one of 'GET' or 'POST'.
		:type uri: ``str``
		:param uri: Endpoint to send the request to. Must not include host.
		:type host: ``str``
		:param host: Host to send to. Defaults to client's _host.
		:type query: ``dict[str, Any]``
		:param query: A map of parameters to insert in the query string.
		:type payload: ``dict | list``
		:param payload: Data payload. Sent as a JSON array if this is a list, or a JSON object if this is a map.
		:type auth: ``bool``
		:param auth: Whether to send an authenticated request. If true, the request will be altered before
		sending it in order to authenticate it to the server. How this is done is up to the exchange client
		implementation.
		:type after: ``(response) -> Any``
		:param after: Function to use to transform the results afterwards.
		:param kwargs: parameters that are passed to the constructor, to override the defaults.
		"""
		encode_payload = kwargs.get('request_payload', self.request_payload)
		decode_payload = kwargs.get('response_payload', self.response_payload)
		ignored_errors = kwargs.get('ignored_errors', self.ignored_errors)
		use_ssl = kwargs.get('ssl', self.ssl)

		prepared = self._prepare_http_request(method, uri, host, query, payload, auth, encode_payload, use_ssl)
		self._async_http_requests.append((prepared, uri, host, auth, decode_payload, ignored_errors))
		self._async_transforms.append(after)

	def clear_async_requests(self):
		"""
		Removes all currently-waiting asynchronous requests without sending them.
		:rtype: HttpAgent
		:return: This HTTP agent.
		"""
		self._async_transforms.clear()
		self._async_http_requests.clear()
		return self

	def send_async_requests(self):
		"""
		Sends all HTTP requests that have been requested by calls to add_async(). Returns when all requests
		have completed. Raises an exception if any of the calls fail, but waits until all are completed before doing so.
		:rtype: ``list[Any]`` A list of the requested items, transformed by their transform function.
		:return:
		"""
		if len(self._async_http_requests) <= 0:
			return ()

		if self._session is None:
			self.start_new_session()
		session = self._session

		responses = [None] * len(self._async_http_requests)
		":type : list"

		futures = []
		for req, uri, host, auth, decode, ignored in self._async_http_requests:
			if host is None:
				host = self._host
			_log_http_request(req, uri, host, auth, self.log_full_request)
			f = self._async_executor.submit(session.send, req)
			# mini data-structure, Tuple[done_yet, future]
			futures.append((False, f, decode, ignored))
		self._async_http_requests = []

		# now wait for them to complete
		while len([x for x in futures if not x[0]]) > 0:
			next_futures = []
			for idx, f in enumerate(futures):
				done_now = f[0]
				if not done_now:
					if f[1].done():
						r = f[1].result()
						_log_http_response(r, self.log_full_response)
						responses[idx] = (r, f[2], f[3])
						done_now = True
				next_futures.append((done_now, f[1], f[2], f[3]))
			futures = next_futures
			time.sleep(0.01)
		# they are now done

		# we need to re-raise any exceptions that occur
		bad_responses = []
		for idx, resp_items in enumerate(responses):
			resp, decode, ignored = resp_items
			if resp.status_code not in ignored:
				try:
					resp.raise_for_status()
				except requests.HTTPError as e:
					_log.exception("HTTPError in request #" + str(idx) + ": " + str(e))
					bad_responses.append(idx)
		if len(bad_responses) > 0:
			self._async_transforms = []
			raise AsyncHTTPError(bad_responses)

		# finally, call the transform function on each one
		transformed = []
		for r_items, xform in zip(responses, self._async_transforms):
			r, decode, ignored = r_items
			data = None
			if r.content is not None:
				if decode == 'text':
					data = r.text
				elif decode == 'json':
					data = r.json(parse_float=decimal.Decimal)
				elif decode == 'binary':
					data = r.content
				else:
					raise ValueError("Bad response_payload encoding: " + decode)
				data = xform(data)
			transformed.append(data)
		self._async_transforms = []
		return transformed

	def request(self, method, uri, host=None, query=None, payload=None, auth=False, **kwargs):
		"""
		Synchronously sends an HTTP request. The response is tested for an error code before it is passed back to the
		caller. If a payload is given, it is The payload is delivered as a JSON object or array, depending on the type
		of the data param.
		:type method: ``str``
		:param method: The HTTP method to use for requesting. Usually one of 'GET' or 'POST'.
		:type uri: ``str``
		:param uri: Endpoint to send the request to. Must not include host.
		:type host: ``str``
		:param host: Host to send to. Defaults to client's _host.
		:type query: ``dict[str, Any]``
		:param query: A map of parameters to insert in the query string.
		:type payload: ``dict | list``
		:param payload: Data payload. Sent as a JSON array if this is a list, or a JSON object if this is a map.
		:type auth: ``bool``
		:param auth: Whether to send an authenticated request. If true, the request will be altered before
		sending it in order to authenticate it to the server. How this is done is up to the exchange client
		implementation.
		:param kwargs: parameters that are passed to the constructor, to override the defaults.
		:rtype: ``(int, dict | list | None)``
		:return: A tuple containing the HTTP status code, and the response payload (which will be a map of data if the
		payload was an object, a list if the payload was an array, or None if the response contained no payload).
		"""
		encode_payload = kwargs.get('request_payload', self.request_payload)
		decode_payload = kwargs.get('response_payload', self.response_payload)
		ignored_errors = kwargs.get('ignored_errors', self.ignored_errors)
		use_ssl = kwargs.get('ssl', self.ssl)

		prepared = self._prepare_http_request(method, uri, host, query, payload, auth, encode_payload, use_ssl)
		if host is None:
			host = self._host
		_log_http_request(prepared, uri, host, auth, self.log_full_request)

		if self._session is None:
			self.start_new_session()
		sess = self._session

		resp = sess.send(prepared)
		_log_http_response(resp, self.log_full_response)

		if resp.status_code not in ignored_errors:
			resp.raise_for_status()  # raise if an error occured (will only raise if the status code is 4XX or 5XX)
		resp_data = None
		if resp.content is not None:
			if decode_payload == 'text':
				resp_data = resp.text
			elif decode_payload == 'json':
				resp_data = resp.json(parse_float=decimal.Decimal)
			elif decode_payload == 'binary':
				resp_data = resp.content
			else:
				raise ValueError("Bad response_payload encoding: " + decode_payload)
		return resp.status_code, resp_data

	def save_cookies(self, filename):
		"""
		Save the cookies in the current session to disk for later retrieval. Can be used to keep logins open across
		launches.
		:param filename: The file to save the cookies to.
		"""
		if self._session is None:
			self.start_new_session()

		cookies = self._session.cookies

		_log.debug('writing out cookies...')

		with open(filename, 'wb') as f:
			pickle.dump(cookies, f)

	def load_cookies(self, filename):
		"""
		Loads the given cookies into the current session. Will replace any current cookies.
		:param filename: The file to load the cookies from.
		"""
		if self._session is None:
			self.start_new_session()

		with open(filename, 'rb') as f:
			cookies = pickle.load(f)

		self._session.cookies.update(cookies)

	@property
	def log_full_request(self):
		"""
		:rtype: bool
		"""
		return self._log_full_request

	@log_full_request.setter
	def log_full_request(self, value):
		"""
		:type value: bool
		"""
		self._log_full_request = value

	@property
	def log_full_response(self):
		"""
		:rtype: bool
		"""
		return self._log_full_response

	@log_full_response.setter
	def log_full_response(self, value):
		"""
		:type value: bool
		"""
		self._log_full_response = value

	@property
	def ssl(self):
		"""
		:rtype: bool
		"""
		return self._use_ssl

	@ssl.setter
	def ssl(self, value):
		"""
		:type value: bool
		"""
		self._use_ssl = value

	@property
	def host(self):
		"""
		:rtype: str
		"""
		return self._host

	@host.setter
	def host(self, value):
		"""
		:type value: str
		"""
		# check for the most common of schemes; all others are on the user.
		if value.startswith('http://') or value.startswith('https://'):
			raise ValueError("scheme must not be included in host")
		self._host = value

	@property
	def request_payload(self):
		"""
		:rtype: str
		"""
		return self._default_request_payload

	@request_payload.setter
	def request_payload(self, value):
		"""
		:type value: str
		"""
		if value != 'json' and value != 'form':
			raise ValueError("request_payload must be one of 'json' or 'form'.")
		self._default_request_payload = value

	@property
	def response_payload(self):
		"""
		:rtype: str
		"""
		return self._default_response_payload

	@response_payload.setter
	def response_payload(self, value):
		"""
		:type value: str
		"""
		if value != 'text' and value != 'json' and value != 'binary':
			raise ValueError("response_payload must be one of 'json', 'text', or 'binary'.")
		self._default_response_payload = value

	@property
	def ignored_errors(self):
		"""
		:rtype: list[int]
		"""
		return list(self._ignored_http_errors)

	@ignored_errors.setter
	def ignored_errors(self, value):
		"""
		:type value: list[int]
		"""
		self._ignored_http_errors = list(value)

	def _prepare_http_request(self, method, uri, host, query, payload, auth, encode_payload, use_ssl):

		if use_ssl:
			scheme = 'https://'
		else:
			scheme = 'http://'

		if host is None:
			host = self._host
		if not uri.startswith('/'):
			uri = '/' + uri

		if encode_payload == 'json':
			json_payload = payload
			form_payload = None
		elif encode_payload == 'form':
			json_payload = None
			form_payload = payload
		else:
			raise ValueError("Bad request_payload encoding: " + encode_payload)

		# requests does not give all headers by default; provide some sane ones here
		headers = _default_http_headers
		full_url = scheme + host + uri
		req = requests.Request(method, full_url, data=form_payload, json=json_payload, params=query, headers=headers)

		# session object will not attach cookies to a prepared request. Do it manually here.
		if self._session is not None:
			req.cookies = self._session.cookies

		if auth:
			prepared = self._auth_func(req)
		else:
			prepared = req.prepare()
		return prepared
