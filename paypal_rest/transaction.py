"""transaction.py - High-level access to PayPal transactions"""
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

import enum

from . import errors

from decimal import Decimal

from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    NamedTuple,
    Optional,
    TypeVar,
    Union,
)
from .paypal_types import (
    Amount,
    APIResponse,
    parse_datetime,
)

T = TypeVar('T')

class CartItem(NamedTuple):
    code: Optional[str]
    name: Optional[str]
    description: Optional[str]
    quantity: Union[int, Decimal]
    unit_price: Amount
    total_price: Amount

    @classmethod
    def from_api(cls, source: APIResponse, default_name: Optional[str]=None) -> 'CartItem':
        total_price = Amount.from_api(source['item_amount'])
        quantity = Decimal(source.get('item_quantity', 1))
        try:
            unit_price = Amount.from_api(source['item_unit_price'])
        except KeyError:
            unit_price = total_price._replace(number=total_price.number / quantity)
        return cls(
            source.get('item_code'),
            source.get('item_name', default_name),
            source.get('item_description'),
            quantity,
            unit_price,
            total_price,
        )


class TransactionStatus(enum.Enum):
    D = "Denied"
    DENIED = D
    F = "Partially Refunded"
    REFUNDED = F
    P = "Pending"
    PENDING = P
    S = "Successful"
    SUCCESSFUL = S
    SUCCESS = S
    V = "Reversed"
    REVERSED = V


class Transaction(APIResponse):
    """PayPal Transaction wrapper

    The public methods of a Transaction know how to traverse PayPal's JSON
    response and turn the data into native Python objects. If Transaction is
    missing a method you need, you can also use standarding Mapping methods to
    access to raw response.
    """
    __slots__ = ['_response']

    def __init__(self, response: APIResponse) -> None:
        self._response = response

    def __getitem__(self, key: str) -> Any:
        return self._response[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._response)

    def __len__(self) -> int:
        return len(self._response)

    def _get_from_response(self, *keys: str) -> Any:
        retval = self._response
        for index, key in enumerate(keys):
            try:
                retval = retval[key]
            except KeyError as error:
                try:
                    txn_id = f"Transaction {self['transaction_info']['transaction_id']}"
                except KeyError:
                    txn_id = "Transaction"
                if index:
                    key_s = '→'.join(repr(key) for key in keys[:index + 1])
                    raise KeyError(f"{txn_id} {key_s}") from None
                else:
                    raise errors.MissingFieldError(
                        f"{txn_id} was not loaded with {error.args[0]!r} field",
                    ) from None
        return retval

    def _wrap_response(  # type:ignore[misc]
            name: str,
            func: Callable[[Any], T],
            *keys: str,
            doc: Optional[str]=None,
            key_doc: Optional[str]=None,
            return_doc: Optional[str]=None,
    ) -> Callable[['Transaction'], T]:
        if doc is None:
            if key_doc is None:
                key_doc = f"``{keys[-1]}``"
            if return_doc is None:
                if name.endswith('amount'):
                    return_doc = 'Amount'
                elif name.endswith('date'):
                    return_doc = 'datetime'
                else:
                    return_doc = func.__name__
            doc = f"Return the transaction's {key_doc} as a ``{return_doc}``"
        def response_wrapper(self: 'Transaction') -> T:
            return func(self._get_from_response(*keys))
        response_wrapper.__name__ = name
        response_wrapper.__doc__ = doc
        return response_wrapper

    def _fee_amount(txn_info: APIResponse) -> Optional[Amount]:  # type:ignore[misc]
        try:
            raw_fee = txn_info['fee_amount']
        except KeyError:
            return None
        else:
            return Amount.from_api(raw_fee)

    amount = _wrap_response(
        'amount',
        Amount.from_api,
        'transaction_info',
        'transaction_amount',
    )
    fee_amount = _wrap_response(
        'fee_amount',
        _fee_amount,
        'transaction_info',
        key_doc='``fee_amount``',
    )
    initiation_date = _wrap_response(
        'initiation_date',
        parse_datetime,
        'transaction_info',
        'transaction_initiation_date',
    )
    payer_email = _wrap_response(
        'payer_email',
        str,
        'payer_info',
        'email_address',
        key_doc="payer's email address",
    )
    payer_fullname = _wrap_response(
        'payer_fullname',
        str,
        'payer_info',
        'payer_name',
        'alternate_full_name',
        key_doc="payer's full name",
    )
    status = _wrap_response(
        'status',
        TransactionStatus.__getitem__,
        'transaction_info',
        'transaction_status',
        return_doc=TransactionStatus.__name__,
    )
    transaction_id = _wrap_response(
        'transaction_id',
        str,
        'transaction_info',
        'transaction_id',
    )
    updated_date = _wrap_response(
        'updated_date',
        parse_datetime,
        'transaction_info',
        'transaction_updated_date',
    )

    def cart_items(self) -> Iterator[CartItem]:
        """Iterate a ``CartItem`` object for each item in the transaction's cart"""
        cart_info = self._get_from_response('cart_info')
        try:
            item_seq = cart_info['item_details']
        except KeyError:
            pass
        else:
            try:
                default_name = self['transaction_info']['transaction_subject']
            except KeyError:
                default_name = None
            for source in item_seq:
                try:
                    yield CartItem.from_api(source, default_name)
                except KeyError:
                    pass
