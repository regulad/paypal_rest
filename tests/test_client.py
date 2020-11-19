"""test_client.py - Unit tests for PayPal API client class"""
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

import datetime
import re

import pytest
import requests

from . import MockSession, MockResponse

from paypal_rest import client as client_mod
from paypal_rest import transaction as txn_mod

START_DATE = datetime.datetime(2020, 10, 1, 12, tzinfo=datetime.timezone.utc)
END_DATE = START_DATE.replace(day=25)

def test_transaction_type():
    txn_id = 'TYPETEST123456789'
    session = MockSession(
        MockResponse({'page': 1, 'total_pages': 1, 'transaction_details': [
            {'transaction_info': {'transaction_id': txn_id}},
        ]}),
    )
    paypal = client_mod.PayPalAPIClient(session)
    txn, = paypal.iter_transactions(START_DATE, END_DATE)
    assert isinstance(txn, txn_mod.Transaction)
    assert txn.transaction_id() == txn_id

@pytest.mark.parametrize('pages', range(1, 4))
def test_transaction_pagination(pages):
    session = MockSession(
        *(MockResponse({'page': page, 'total_pages': pages, 'transaction_details': []})
          for page in range(1, pages + 1))
    )
    paypal = client_mod.PayPalAPIClient(session)
    actual = list(paypal.iter_transactions(START_DATE, END_DATE))
    assert len(session._requests) == pages
    for expect_page, request in enumerate(session._requests, 1):
        assert request.params.get('page') == str(expect_page)

@pytest.mark.parametrize('index,key', enumerate(['start_date', 'end_date']))
def test_transaction_date_formatting(index, key):
    session = MockSession(
        MockResponse({'page': 1, 'total_pages': 1, 'transaction_details': []}),
    )
    paypal = client_mod.PayPalAPIClient(session)
    args = [START_DATE, END_DATE]
    new_date = START_DATE.replace(day=15)
    args[index] = new_date
    actual = list(paypal.iter_transactions(*args))
    assert session._requests
    assert session._requests[0].params.get(key) == new_date.isoformat(timespec='seconds')

@pytest.mark.parametrize('fields', [
    {'transaction'},
    {'cart'},
    {'transaction', 'payer'},
    {'cart', 'transaction', 'payer'},
])
def test_transaction_fields_formatting(fields):
    fields_iter = (name.upper() for name in fields)
    fields_arg = client_mod.TransactionFields[next(fields_iter)]
    for name in fields_iter:
        fields_arg |= client_mod.TransactionFields[name]
    session = MockSession(
        MockResponse({'page': 1, 'total_pages': 1, 'transaction_details': []}),
    )
    paypal = client_mod.PayPalAPIClient(session)
    _ = list(paypal.iter_transactions(START_DATE, END_DATE, fields_arg))
    assert session._requests
    assert fields == {
        re.sub(r'_info$', '', name)
        for name in session._requests[0].params.get('fields', '').split(',')
    }

@pytest.mark.parametrize('days_diff', [10, 45, 89])
def test_iter_transactions_date_window(days_diff):
    start_date = START_DATE
    end_date = start_date + datetime.timedelta(days=days_diff)
    session = MockSession(
        MockResponse({'page': 1, 'total_pages': 1, 'transaction_details': []}),
        infinite=True,
    )
    paypal = client_mod.PayPalAPIClient(session)
    assert not any(paypal.iter_transactions(start_date, end_date))
    req_count = len(session._requests)
    assert req_count == ((days_diff // 30) + 1)
    start_str = start_date.isoformat(timespec='seconds')
    end_str = end_date.isoformat(timespec='seconds')
    prev_end = start_str
    for number, request in enumerate(session._requests, 1):
        assert request.params['start_date'] == prev_end
        if number == req_count:
            assert request.params['end_date'] == end_str
        else:
            assert prev_end < request.params['end_date'] < end_str
            prev_end = request.params['end_date']

@pytest.mark.parametrize('days_diff', [10, 45, 89])
def test_get_transactions_date_window(days_diff):
    end_date = END_DATE
    start_date = end_date - datetime.timedelta(days=days_diff)
    session = MockSession(
        MockResponse({'page': 1, 'total_pages': 1, 'transaction_details': []}),
        infinite=True,
    )
    paypal = client_mod.PayPalAPIClient(session)
    with pytest.raises(ValueError):
        paypal.get_transaction('DATEWINDOW1234567', end_date, start_date)
    req_count = len(session._requests)
    assert req_count == ((days_diff // 30) + 1)
    start_str = start_date.isoformat(timespec='seconds')
    end_str = end_date.isoformat(timespec='seconds')
    prev_start = end_str
    for number, request in enumerate(session._requests, 1):
        assert request.params['end_date'] == prev_start
        if number == req_count:
            assert request.params['start_date'] == start_str
        else:
            assert prev_start > request.params['start_date'] > start_str
            prev_start = request.params['start_date']

@pytest.mark.parametrize('name', [
    'BAD_REQUEST',
    'UNAUTHORIZED',
    'FORBIDDEN',
    'NOT_FOUND',
    'INTERNAL_SERVER_ERROR',
])
def test_error_handling(name, caplog):
    session = MockSession(MockResponse.error(name, status_code=requests.codes[name]))
    paypal = client_mod.PayPalAPIClient(session)
    with pytest.raises(requests.HTTPError):
        paypal.get_transaction('ABCDEFGHIJKLMNOPQ')
    assert any(
        log.levelname == 'ERROR'
        and log.message == f'{name}: Test error'
        for log in caplog.records
    )
