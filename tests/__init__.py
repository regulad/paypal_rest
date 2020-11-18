"""__init__.py - paypal_rest unit test common functionality"""
# Copyright © 2020  Brett Smith
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import itertools
import typing
import urllib.parse as urlparse

import requests

FLOAT_NUMBERS = [
    '1200.30',
    '255.75',
    '99.99',
    '5.00',
    '0.00',
]
FLOAT_NUMBERS.extend(f'-{s}' for s in FLOAT_NUMBERS[:-1])

WHOLE_NUMBERS = [
    '1250',
    '255',
    '99',
    '5',
    '0',
]
WHOLE_NUMBERS.extend(f'-{s}' for s in WHOLE_NUMBERS[:-1])

class ReceivedRequest(typing.NamedTuple):
    method: str
    url: urlparse.ParseResult
    params: typing.Mapping[str, str]

    @classmethod
    def from_args(cls, method, url, params):
        return cls(
            method,
            urlparse.urlparse(url),
            dict(params or ()),
        )


class MockResponse:
    def __init__(self, body, status_code=requests.codes.OK):
        self._body = body
        self.status_code = status_code

    @classmethod
    def error(
            cls,
            name='TEST_ERROR',
            message='Test error',
            debug_id='0000',
            status_code=requests.codes.BAD_REQUEST,
            *details,
            **kwargs,
    ):
        body = {
            'name': name,
            'message': message,
            'debug_id': debug_id,
            'details': [{'issue': issue, 'location': 'test'}
                        for issue in details],
        }
        body.update(kwargs)
        return cls(body, status_code)

    def json(self):
        return self._body.copy()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


class MockSession:
    LAST_RESPONSE = MockResponse({
        'name': 'NO_RESPONSE',
        'message': 'MockSession got more requests than expected',
    }, 509)

    def __init__(self, *responses, infinite=False):
        self._requests = []
        if infinite:
            self._responses = itertools.cycle(responses)
        else:
            self._responses = itertools.chain(
                responses,
                itertools.repeat(self.LAST_RESPONSE),
            )

    def request(self, method, url, params=None):
        self._requests.append(ReceivedRequest.from_args(method, url, params))
        return next(self._responses)

    def get(self, url, params=None):
        return self.request('GET', url, params)
