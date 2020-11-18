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
import functools
import logging
import math
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
    @classmethod
    def choices(cls) -> Iterator[str]:
        for flag in cls:
            yield flag.name.lower()

    @classmethod
    def combine(cls: Type[FieldsType], fields: Optional[Sequence[FieldsType]]=None) -> FieldsType:
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
        try:
            return cls[arg.upper()]
        except KeyError:
            raise ValueError(f"unknown {cls.__name__} {arg!r}") from None

    def is_base_field(self) -> bool:
        return not math.log2(self.value) % 1

    def _base_value(self) -> str:
        return self.name.lower()

    def param_value(self) -> str:
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
    def __init__(
            self,
            session: requests.Session,
            root_url: Union[str, PayPalSite]=PayPalSite.SANDBOX,
            logger: Optional[logging.Logger]=None,
    ) -> None:
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

    def get_subscription(
            self,
            subscription_id: str,
            fields: SubscriptionFields=SubscriptionFields.ALL,
    ) -> APIResponse:
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
        now = datetime.datetime.now(datetime.timezone.utc)
        if end_date is None:
            end_date = now
        if start_date is None:
            # The API only goes back three years
            start_date = now - datetime.timedelta(days=365 * 3)
        date_diff = datetime.timedelta(days=30)
        response: APIResponse = {'transaction_details': None}
        while end_date > start_date and not response['transaction_details']:
            search_start = max(end_date - date_diff, start_date)
            response = self._get_json('/v1/reporting/transactions', {
                'transaction_id': transaction_id,
                'fields': fields.param_value(),
                'start_date': search_start.isoformat(timespec='seconds'),
                'end_date': end_date.isoformat(timespec='seconds'),
            })
            end_date = search_start
        if response['transaction_details']:
            return Transaction(response['transaction_details'][0])
        else:
            raise ValueError(f"transaction {transaction_id!r} not found")

    def iter_transactions(
            self,
            start_date: datetime.datetime,
            end_date: datetime.datetime,
            fields: TransactionFields=TransactionFields.TRANSACTION,
    ) -> Iterator[Transaction]:
        for page in self._iter_pages('/v1/reporting/transactions', {
                'fields': fields.param_value(),
                'start_date': start_date.isoformat(timespec='seconds'),
                'end_date': end_date.isoformat(timespec='seconds'),
        }):
            for txn_source in page['transaction_details']:
                yield Transaction(txn_source)
