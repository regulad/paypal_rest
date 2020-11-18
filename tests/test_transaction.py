"""test_transaction.py - Unit tests for high-level Transaction access"""
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

from decimal import Decimal

import pytest
import requests

from . import MockSession, MockResponse, FLOAT_NUMBERS, WHOLE_NUMBERS

from paypal_rest import errors
from paypal_rest import transaction as txn_mod

DATE1 = datetime.datetime(2020, 10, 2, 14, 15, 16, tzinfo=datetime.timezone.utc)
DATE2 = DATE1.replace(second=56)

def item_source(
        name=None,
        description=None,
        code=None,
        quantity=1,
        number='15.99',
        currency='USD',
):
    if description is None:
        description = name
    if code is None:
        code = name
    total_number = str(quantity * Decimal(number))
    retval = {
        'item_quantity': str(quantity),
        'item_unit_price': {'value': number, 'currency_code': currency},
        'item_item_amount': {'value': total_number, 'currency_code': currency},
        'item_amount': {'value': total_number, 'currency_code': currency},
    }
    if name is not None:
        retval['item_name'] = name
    if description is not None:
        retval['item_description'] = description
    if code is not None:
        retval['item_code'] = code
    return retval

def cart_info(*item_kwargs):
    return {'item_details': [item_source(**kwargs) for kwargs in item_kwargs]}

def payer_info(
        given_name='Payer',
        surname='Smith',
        account_id='PAYER12345678',
        payer_status='Y',
        address_status='Y',
        country_code='US',
        email_address='payer@example.org',
):
    retval = locals().copy()
    del retval['given_name'], retval['surname']
    retval['payer_name'] = {
        'given_name': given_name,
        'surname': surname,
        'alternate_full_name': f'{given_name} {surname}',
    }
    return retval

def transaction_info(
        transaction_id='TRANSACTION123456',
        number='5.00',
        currency='USD',
        fee_number='-0.49',
        fee_currency=None,
        init_date=DATE1,
        update_date=None,
        status='S',
        subject=None,
        note=None,
):
    retval = {
        'transaction_id': transaction_id,
        'transaction_status': status,
        'transaction_initiation_date': init_date.isoformat(timespec='seconds'),
        'transaction_updated_date': (update_date or init_date).isoformat(timespec='seconds'),
        'transaction_amount': {'value': number, 'currency_code': currency},
        'fee_amount': {'value': fee_number, 'currency_code': fee_currency or currency},
    }
    if subject is not None:
        retval['transaction_subject'] = subject
    if note is not None:
        retval['transaction_note'] = note
    return retval

def test_mapping():
    source = {
        'transaction_info': transaction_info(),
        'payer_info': payer_info(),
    }
    txn = txn_mod.Transaction(source.copy())
    assert len(txn) == len(source)
    assert frozenset(txn) == frozenset(source)
    assert txn == source
    assert txn.get('test_key') is None

@pytest.mark.parametrize('number', FLOAT_NUMBERS)
def test_amount_float(number):
    source = transaction_info(number=number, currency='USD')
    txn = txn_mod.Transaction({'transaction_info': source})
    assert txn.amount() == (Decimal(number), 'USD')

@pytest.mark.parametrize('number', WHOLE_NUMBERS)
def test_amount_whole(number):
    source = transaction_info(number=number, currency='JPY')
    txn = txn_mod.Transaction({'transaction_info': source})
    assert txn.amount() == (int(number), 'JPY')

def test_cart_items():
    source = cart_info(
        {'number': '5.99'},
        {'name': 'Test', 'number': '7.99', 'quantity': 2},
    )
    txn = txn_mod.Transaction({'cart_info': source})
    item1, item2 = txn.cart_items()
    item1_price = (Decimal('5.99'), 'USD')
    assert item1 == (
        None, None, None, 1, item1_price, item1_price,
    )
    assert item2 == (
        'Test', 'Test', 'Test', 2,
        (Decimal('7.99'), 'USD'),
        (Decimal('15.98'), 'USD'),
    )

@pytest.mark.parametrize('subject', [
    'test subject',
    '$6.99 Subscription',
    None,
])
def test_unnamed_cart_item_uses_transaction_subject(subject):
    source = {
        'cart_info': cart_info({'number': '6.99'}),
        'transaction_info': transaction_info(subject=subject),
    }
    txn = txn_mod.Transaction(source)
    item1, = txn.cart_items()
    assert item1.name == subject

def test_cart_empty():
    txn = txn_mod.Transaction({'cart_info': {}})
    assert not any(txn.cart_items())

def test_cart_quantity_only():
    # Refunds are structured this way.
    source = {'item_details': [{'item_quantity': '1.000'}]}
    txn = txn_mod.Transaction({'cart_info': source})
    assert not any(txn.cart_items())

@pytest.mark.parametrize('number', FLOAT_NUMBERS)
def test_fee_amount_float(number):
    source = transaction_info(fee_number=number, fee_currency='USD')
    txn = txn_mod.Transaction({'transaction_info': source})
    assert txn.fee_amount() == (Decimal(number), 'USD')

@pytest.mark.parametrize('number', WHOLE_NUMBERS)
def test_fee_amount_whole(number):
    source = transaction_info(fee_number=number, fee_currency='JPY')
    txn = txn_mod.Transaction({'transaction_info': source})
    assert txn.fee_amount() == (int(number), 'JPY')

def test_fee_amount_none():
    txn = txn_mod.Transaction({'transaction_info': {}})
    assert txn.fee_amount() is None

def test_payer_email():
    email = 'test@example.net'
    source = payer_info(email_address=email)
    txn = txn_mod.Transaction({'payer_info': source})
    assert txn.payer_email() == email

@pytest.mark.parametrize('given_name', ['Robin', 'Sawyer'])
def test_payer_fullname(given_name):
    txn = txn_mod.Transaction({'payer_info': payer_info(given_name)})
    assert txn.payer_fullname() == f'{given_name} Smith'

def test_initiation_date():
    source = transaction_info(init_date=DATE2)
    txn = txn_mod.Transaction({'transaction_info': source})
    assert txn.initiation_date() == DATE2

@pytest.mark.parametrize('key', 'DFPSV')
def test_status(key):
    source = transaction_info(status=key)
    txn = txn_mod.Transaction({'transaction_info': source})
    assert txn.status() is txn_mod.TransactionStatus[key]

def test_transaction_id():
    test_id = 'TESTTXNID12345678'
    source = transaction_info(transaction_id=test_id)
    txn = txn_mod.Transaction({'transaction_info': source})
    assert txn.transaction_id() == test_id

def test_updated_date():
    source = transaction_info(update_date=DATE2)
    txn = txn_mod.Transaction({'transaction_info': source})
    assert txn.updated_date() == DATE2

@pytest.mark.parametrize('method_name', [
    'amount',
    'cart_items',
    'fee_amount',
    'payer_email',
    'payer_fullname',
    'initiation_date',
    'status',
    'transaction_id',
    'updated_date',
])
def test_info_missing(method_name):
    txn = txn_mod.Transaction({})
    with pytest.raises(errors.MissingFieldError):
        result = getattr(txn, method_name)()
        try:
            do_next = iter(result) is result
        except TypeError:
            do_next = False
        if do_next:
            next(result)
