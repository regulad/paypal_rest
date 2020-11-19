"""client.py - PayPal API client class"""
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

import collections
import datetime
import enum
import logging
import math
import operator
import urllib.parse as urlparse

import requests
import requests_oauthlib  # type:ignore[import]
from oauthlib import oauth2  # type:ignore[import]

from typing import (
    Any,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)
from .paypal_types import (
    APIResponse,
)
from .transaction import Transaction

FieldsType = TypeVar('FieldsType', bound='PayPalFields')
Params = Mapping[str, str]

class PayPalSite(enum.Enum):
    SANDBOX = 'api-m.sandbox.paypal.com'
    LIVE = 'api-m.paypal.com'

    def url(self) -> str:
        return f'https://{self.value}'


class PayPalFields(enum.Flag):
    """Base class for PayPal fields specifiers

    Multiple PayPal APIs accept a ``fields`` parameter to let the user specify
    what details to return. This class lets code enumerate acceptable values
    and combine them programmatically. The ``param_value`` method then helps
    ``PayPalAPIClient`` format the result when needed.
    """

    @classmethod
    def choices(cls) -> Iterator[str]:
        """Iterate the names of all field values"""
        for flag in cls:
            yield flag.name.lower()

    @classmethod
    def combine(cls: Type[FieldsType], fields: Optional[Sequence[FieldsType]]=None) -> FieldsType:
        """Combine multiple field objects into one

        This method just returns the result of ORing all of the fields in the
        sequence together. If no argument is given or the sequence is empty,
        return the combination of all fields.
        """
        if fields:
            fields_iter = iter(fields)
        else:
            fields_iter = iter(cls)
        retval = next(fields_iter)
        for field in fields_iter:
            retval |= field
        return retval

    @classmethod
    def from_arg(cls: Type[FieldsType], arg: str) -> FieldsType:
        """Return a field object from an argument name string"""
        try:
            return cls[arg.upper()]
        except KeyError:
            raise ValueError(f"unknown {cls.__name__} {arg!r}") from None

    def is_base_field(self) -> bool:
        """Return true if this is a single field value, not a combination"""
        return not math.log2(self.value) % 1

    def _base_value(self) -> str:
        return self.name.lower()

    def param_value(self) -> str:
        """Return these fields formatted as a query string

        The result is in the format PayPal's API expects for ``fields``
        parameters.
        """
        return ','.join(
            flag._base_value()
            for flag in type(self)
            if flag & self and flag.is_base_field()
        )


class SubscriptionFields(PayPalFields):
    LAST_FAILED_PAYMENT = enum.auto()
    PLAN = enum.auto()
    ALL = LAST_FAILED_PAYMENT | PLAN


class TransactionFields(PayPalFields):
    TRANSACTION = enum.auto()
    PAYER = enum.auto()
    SHIPPING = enum.auto()
    AUCTION = enum.auto()
    CART = enum.auto()
    INCENTIVE = enum.auto()
    STORE = enum.auto()
    ALL = TRANSACTION | PAYER | SHIPPING | AUCTION | CART | INCENTIVE | STORE

    def _base_value(self) -> str:
        return f'{self.name.lower()}_info'


class PayPalSession(requests_oauthlib.OAuth2Session):
    """Low-level HTTP session for the PayPal API

    This is a subclass of requests_oauthlib.OAuth2Session that implements
    PayPal's recommended authorization strategy: if an API request returns
    HTTP Unauthorized, get an OAuth token and retry. This gracefully handles
    refreshing expired tokens.

    This class only handles the mechanics of handling an HTTP connection.
    It doesn't know anything about the higher-level REST API. That's the job
    of ``PayPalAPIClient``.
    """
    TOKEN_PATH = '/v1/oauth2/token'

    def __init__(self, client: oauth2.Client, client_secret: str) -> None:
        super().__init__(client=client)
        self._client_secret = client_secret

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        response = super().request(method, url, **kwargs)
        if response.status_code == requests.codes.UNAUTHORIZED:
            self.fetch_token(
                token_url=urlparse.urljoin(url, self.TOKEN_PATH),
                client_id=self._client.client_id,
                client_secret=self._client_secret,
            )
            response = super().request(method, url, **kwargs)
        return response


class PayPalAPIClient:
    """Primary access point for the PayPal API

    This is the primary class of the library. Most users will instantiate a
    ``PayPalAPIClient`` using one of the constructor classmethods, then call
    methods to make API calls.
    """

    def __init__(
            self,
            session: requests.Session,
            root_url: Union[str, PayPalSite]=PayPalSite.SANDBOX,
            logger: Optional[logging.Logger]=None,
    ) -> None:
        """Low-level constructor

        ``PayPalAPIClient`` expects its underlying ``Session`` object to know
        how to authorize itself to PayPal. Usually that means using an instance
        of ``PayPalSession``. You can implement and provide your own subclass
        of ``requests.Session`` to do this if you prefer.

        ``root_url`` is either a PayPalSite value, or a string with a full URL
        to a PayPal API endpoint.

        ``logger`` is a ``logging.Logger`` object where all log messages (like
        API errors) will be sent. If none is provided, this instance will get
        its own, with a name based on the hostname in ``root_url``.
        """
        self._session = session
        if isinstance(root_url, str):
            self._root_url = root_url
        else:
            self._root_url = root_url.url()
        if logger is None:
            host_parts = urlparse.urlsplit(self._root_url).netloc.split('.')
            host_parts.reverse()
            logger_name = f'paypal_rest.PayPalAPIClient.{".".join(host_parts)}'
            logger = logging.getLogger(logger_name)
        self.logger = logger

    @classmethod
    def from_client_secret(
            cls,
            client_id: str,
            client_secret: str,
            root_url: Union[str, PayPalSite]=PayPalSite.SANDBOX,
            logger: Optional[logging.Logger]=None,
    ) -> 'PayPalAPIClient':
        """High-level constructor from individual string arguments

        Given ``client_id`` and ``client_secret`` strings, this method
        constructs a ``PayPalSesssion`` from them, and then returns a
        ``PayPalAPIClient`` backed by it.

        ``root_url`` and ``logger`` arguments are passed directly to
        ``PayPalAPIClient.__init__``.
        """
        client = oauth2.BackendApplicationClient(client_id=client_id)
        session = PayPalSession(client, client_secret)
        return cls(session, root_url, logger)

    @classmethod
    def from_config(
            cls,
            config: Mapping[str, str],
            default_url: Union[str, PayPalSite]=PayPalSite.SANDBOX,
            logger: Optional[logging.Logger]=None,
    ) -> 'PayPalAPIClient':
        """High-level constructor from a configuration mapping

        Given a mapping of strings (e.g., a configparser section object),
        gets the arguments necessary to call ``from_client_secret``, and calls
        it.

        If the mapping has a ``site`` key, the value will be used as the
        ``root_url``. Otherwise, ``root_url`` has the value of ``default_url``.

        ``logger`` is passed directly to ``PayPalAPIClient.__init__``.
        """
        try:
            client_id = config['client_id']
            client_secret = config['client_secret']
        except KeyError as error:
            raise ValueError(f"configuration missing {error.args[0]!r}") from None
        try:
            root_url: Union[str, PayPalSite] = config['site']
        except KeyError:
            root_url = default_url
        else:
            try:
                # In this case, we know root_url must be a str because we got
                # it from the Mapping, but mypy doesn't track that.
                root_url = PayPalSite[root_url.upper()]  # type:ignore[union-attr]
            except KeyError:
                pass
        return cls.from_client_secret(client_id, client_secret, root_url, logger)

    def _get_json(self, path: str, params: Optional[Params]=None) -> APIResponse:
        url = urlparse.urljoin(self._root_url, path)
        response = self._session.get(url, params=params)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            self._log_error(response.json())
            raise
        else:
            return response.json()

    def _iter_pages(self, path: str, params: Params) -> Iterator[APIResponse]:
        response: APIResponse = {'page': 0, 'total_pages': 1}
        page_params = collections.ChainMap(params).new_child()
        while response['page'] < response['total_pages']:
            page_params['page'] = str(response['page'] + 1)
            response = self._get_json(path, page_params)
            yield response

    def _log_error(self, error: APIResponse) -> None:
        parts = [
            '{name}: {message}'.format_map(error),
            *('{issue} (in {location})'.format_map(detail)
              for detail in error.get('details', ())),
        ]
        self.logger.error(" — ".join(parts))

    def _iter_date_params(
            self,
            start_date: datetime.datetime,
            end_date: datetime.datetime,
            params: Optional[Params]=None,
    ) -> Iterator[Params]:
        """Generate parameters with date windows to cover a wider span

        The PayPal transaction search API only allows the ``start_date`` and
        ``end_date`` to be a month apart. Given a user's desired date range and
        other API parameters, this method generates parameters with different
        date pairs to cover the entire date range.

        Normally the method keeps incrementing ``start_date`` until the user's
        desired ``end_date`` is reached. If the ``start_date`` if later than the
        ``end_date``, instead it works backwards: it uses the ``start_date``
        argument as the first ``end_date`` parameter, and keeps decrementing it
        until the ``start_date`` parameter reaches the other end of the range.
        """
        if start_date > end_date:
            key1 = 'end_date'
            key2 = 'start_date'
            days_sign = operator.neg
            pred = operator.gt
            limit_func = max
        else:
            key1 = 'start_date'
            key2 = 'end_date'
            days_sign = operator.pos
            pred = operator.lt
            limit_func = min
        retval = collections.ChainMap(params or {}).new_child()
        retval[key1] = start_date.isoformat(timespec='seconds')
        next_date = start_date
        date_diff = datetime.timedelta(days=days_sign(30))
        while pred(next_date, end_date):
            next_date = limit_func(next_date + date_diff, end_date)
            retval[key2] = next_date.isoformat(timespec='seconds')
            yield retval
            retval[key1] = retval[key2]

    def get_subscription(
            self,
            subscription_id: str,
            fields: SubscriptionFields=SubscriptionFields.ALL,
    ) -> APIResponse:
        """Fetch and return a subscription by its id"""
        return self._get_json(f'/v1/billing/subscriptions/{subscription_id}', {
            'fields': fields.param_value(),
        })

    def get_transaction(
            self,
            transaction_id: str,
            end_date: Optional[datetime.datetime]=None,
            start_date: Optional[datetime.datetime]=None,
            fields: TransactionFields=TransactionFields.TRANSACTION,
    ) -> APIResponse:
        """Find and return a transaction by its id

        The PayPal API does not provide a way to look up transactions solely by
        id. This is a convenience method that wraps the search method to search
        different windows of time until it finds the desired transaction.

        ``start_date`` and ``end_date`` specify the full window of time to
        search. This method starts by searching 30 days before ``end_date``,
        then the previous 30 days, and so on until it reaches ``start_date``.
        The default ``end_date`` is now, and the default ``start_date`` is
        three years ago (the API only supports searches this far back).

        ``fields`` is a TransactionFields object that flags the information to
        include in the returned Transaction.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        if end_date is None:
            end_date = now
        if start_date is None:
            # The API only goes back three years
            start_date = now - datetime.timedelta(days=365 * 3)
        response: APIResponse = {'transaction_details': None}
        for params in self._iter_date_params(end_date, start_date, {
                'transaction_id': transaction_id,
                'fields': fields.param_value(),
        }):
            response = self._get_json('/v1/reporting/transactions', params)
            if response['transaction_details']:
                return Transaction(response['transaction_details'][0])
        raise ValueError(f"transaction {transaction_id!r} not found")

    def iter_transactions(
            self,
            start_date: datetime.datetime,
            end_date: datetime.datetime,
            fields: TransactionFields=TransactionFields.TRANSACTION,
    ) -> Iterator[Transaction]:
        """Iterate transactions over a date range

        ``start_date`` and ``end_date`` represent the range to query.
        ``fields`` is a TransactionsFields object that flags the information to
        include in returned Transactions.
        """
        for params in self._iter_date_params(start_date, end_date, {
                'fields': fields.param_value(),
        }):
            for page in self._iter_pages('/v1/reporting/transactions', params):
                for txn_source in page['transaction_details']:
                    yield Transaction(txn_source)
