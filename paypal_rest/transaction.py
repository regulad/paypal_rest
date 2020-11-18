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
    def from_api(cls, source: APIResponse) -> 'CartItem':
        total_price = Amount.from_api(source['item_amount'])
        quantity = Decimal(source.get('item_quantity', 1))
        try:
            unit_price = Amount.from_api(source['item_unit_price'])
        except KeyError:
            unit_price = total_price._replace(number=total_price.number / quantity)
        return cls(
            source.get('item_code'),
            source.get('item_name'),
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
    __slots__ = ['_response']

    def __init__(self, response: APIResponse) -> None:
        self._response = response

    def __getitem__(self, key: str) -> Any:
        return self._response[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._response)

    def __len__(self) -> int:
        return len(self._response)

    def _from_response(  # type:ignore[misc]
            func: Callable[[Any], T],
            *keys: str,
    ) -> Callable[['Transaction'], T]:
        def _load_from_response(self: 'Transaction') -> T:
            source = self._response
            for index, key in enumerate(keys):
                try:
                    source = source[key]
                except KeyError as error:
                    try:
                        txn_id = f"Transaction {self['transaction_info']['transaction_id']}"
                    except KeyError:
                        txn_id = "Transaction"
                    if source is self._response:
                        raise errors.MissingFieldError(
                            f"{txn_id} was not loaded with {error.args[0]!r} field",
                        ) from None
                    else:
                        key_s = '→'.join(repr(key) for key in keys[:index + 1])
                        raise KeyError(f"{txn_id} {key_s}") from None
            return func(source)
        return _load_from_response

    def _cart_items(cart_info: APIResponse) -> Iterator[CartItem]:  # type:ignore[misc]
        try:
            item_seq = cart_info['item_details']
        except KeyError:
            pass
        else:
            for source in item_seq:
                try:
                    yield CartItem.from_api(source)
                except KeyError:
                    pass

    def _fee_amount(txn_info: APIResponse) -> Optional[Amount]:  # type:ignore[misc]
        try:
            raw_fee = txn_info['fee_amount']
        except KeyError:
            return None
        else:
            return Amount.from_api(raw_fee)

    amount = _from_response(
        Amount.from_api,
        'transaction_info',
        'transaction_amount',
    )
    cart_items = _from_response(_cart_items, 'cart_info')
    fee_amount = _from_response(_fee_amount, 'transaction_info')
    initiation_date = _from_response(
        parse_datetime,
        'transaction_info',
        'transaction_initiation_date',
    )
    payer_email = _from_response(str, 'payer_info', 'email_address')
    payer_fullname = _from_response(str, 'payer_info', 'payer_name', 'alternate_full_name')
    status = _from_response(
        TransactionStatus.__getitem__,
        'transaction_info',
        'transaction_status',
    )
    transaction_id = _from_response(str, 'transaction_info', 'transaction_id')
    updated_date = _from_response(
        parse_datetime,
        'transaction_info',
        'transaction_updated_date',
    )
