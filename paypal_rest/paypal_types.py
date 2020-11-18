"""paypal_types.py - Common types and classes across the PayPal API"""
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

from decimal import Decimal

from typing import (
    Any,
    Callable,
    Mapping,
    NamedTuple,
)

# Declare a type definition for the one function of iso8601 that we use.
import iso8601  # type:ignore[import]
parse_datetime: Callable[[str], datetime.datetime] = iso8601.parse_date

APIResponse = Mapping[str, Any]

class Amount(NamedTuple):
    number: Decimal
    currency: str

    @classmethod
    def from_api(cls, source: APIResponse) -> 'Amount':
        return cls(
            Decimal(source['value']),
            source['currency_code'],
        )

    def __str__(self) -> str:
        return '{:,g} {}'.format(*self)
