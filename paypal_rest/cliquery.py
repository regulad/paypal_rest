#!/usr/bin/env python3
"""cliquery.py - Command line tool to query PayPal transactions and subscriptions"""
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

import argparse
import collections
import datetime
import logging
import sys

from pathlib import Path
import yaml

from . import client as clientmod
from . import cliutil
from . import config as configmod
from . import paypal_types
from .transaction import CartItem, Transaction

from typing import (
    Optional,
    Sequence,
    TextIO,
    Type,
)

PROGNAME = 'paypal-query'

logger = logging.getLogger('paypal_rest.cliquery')

class YAMLDumper(yaml.SafeDumper):
    TRANSACTION_FIELD_ORDER = [
        clientmod.TransactionFields.SHIPPING,
        clientmod.TransactionFields.PAYER,
        clientmod.TransactionFields.TRANSACTION,
        clientmod.TransactionFields.CART,
        clientmod.TransactionFields.STORE,
        clientmod.TransactionFields.AUCTION,
        clientmod.TransactionFields.INCENTIVE,
    ]

    @classmethod
    def add_transaction_representer(cls, fields: clientmod.TransactionFields) -> None:
        txn_key_order = [
            f'{flag.name.lower()}_info'
            for flag in cls.TRANSACTION_FIELD_ORDER
            if flag & fields
        ]
        def transaction_representer(self: 'YAMLDumper', data: Transaction) -> yaml.nodes.MappingNode:
            return self.represent_dict((key, data[key]) for key in txn_key_order)
        cls.add_representer(Transaction, transaction_representer)


def add_fields_argument(
        parser: argparse.ArgumentParser,
        field_type: Type[clientmod.PayPalFields],
        *short_flags: str,
) -> argparse.Action:
    type_name = field_type.__name__[:-6].lower()
    return parser.add_argument(
        f'--{type_name}-fields', *short_flags,
        action='append',
        metavar='FIELD',
        type=field_type.from_arg,
        help=f"Only show these field(s) in {type_name} results."
        " You can specify this option multiple times."
        f" Choices are {', '.join(field_type.choices())}."
    )

def parse_arguments(arglist: Optional[Sequence[str]]=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=PROGNAME)
    cliutil.add_version_argument(parser)
    parser.add_argument(
        '--config-file', '-C',
        type=Path,
        metavar='PATH',
        help="""Read client configuration from this INI file
""")
    parser.add_argument(
        '--config-section', '-c',
        default='query',
        help="""Read client configuration from this section of the config file
""")
    parser.add_argument(
        '--begin', '--start', '-b',
        dest='start_date',
        metavar='DATETIME',
        type=paypal_types.parse_datetime,
        help="""Datetime to begin the search, in ISO 8601 format
""")
    parser.add_argument(
        '--end', '--stop', '-e',
        dest='end_date',
        metavar='DATETIME',
        type=paypal_types.parse_datetime,
        help="""Datetime to end the search, in ISO 8601 format
""")
    add_fields_argument(parser, clientmod.TransactionFields, '--txn-fields', '-T')
    add_fields_argument(parser, clientmod.SubscriptionFields, '--sub-fields', '-S')
    parser.add_argument(
        'paypal_ids',
        metavar='ID',
        nargs='*',
        help="""ID of PayPal object(s) to look up and return. If no IDs are
specified, lists all transactions in your specified date range (default last
24 hours).
""")
    cliutil.add_loglevel_argument(parser)
    args = parser.parse_args(arglist)
    args.transaction_fields = clientmod.TransactionFields.combine(args.transaction_fields)
    args.subscription_fields = clientmod.SubscriptionFields.combine(args.subscription_fields)
    if args.end_date is None:
        args.end_date = datetime.datetime.now(datetime.timezone.utc)
    return args

def summarize_transaction(txn: Transaction, stream: TextIO) -> None:
    date_s = txn.updated_date().astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
    status = txn.status().value
    try:
        from_s = f"\t{txn.payer_fullname()} ({txn.payer_email()})"
    except KeyError:
        from_s = ""
    print(f"{date_s}\t{txn.transaction_id()}\t{status}{from_s}", file=stream)
    cart = list(txn.cart_items())
    if not cart:
        txn_name = txn['transaction_info'].get('transaction_subject', "Gross Amount")
        txn_amt = txn.amount()
        cart.append(CartItem(None, txn_name, None, 1, txn_amt, txn_amt))
    fee_amt = txn.fee_amount()
    if fee_amt is not None:
        cart.append(CartItem(None, "PayPal Fee", None, 1, fee_amt, fee_amt))
    names = [
        item.name or item.description or item.code or "Unknown Item"
        for item in cart
    ]
    amounts = [str(item.total_price) for item in cart]
    name_len = max(len(name) for name in names)
    amt_len = max(len(amt_s) for amt_s in amounts)
    line_fmt = f'  {{:>{name_len}}} │ {{:>{amt_len}}}{{}}'
    for item, name, amt_s in zip(cart, names, amounts):
        if item.quantity != 1:
            unit_s = f" ({item.quantity:,g} @ {item.unit_price})"
        else:
            unit_s = ""
        print(line_fmt.format(name, amt_s, unit_s), file=stream)

def main(
        arglist: Optional[Sequence[str]]=None,
        stdout: TextIO=sys.stdout,
        stderr: TextIO=sys.stderr,
) -> int:
    args = parse_arguments(arglist)
    cliutil.set_loglevel(logger, args.loglevel)

    config = configmod.load_config(args.config_file)
    if args.config_section not in config:
        config.add_section(args.config_section)
    paypal = clientmod.PayPalAPIClient.from_config(config[args.config_section])

    if not args.paypal_ids:
        if args.start_date is None:
            args.start_date = args.end_date - datetime.timedelta(hours=24)
        args.transaction_fields |= clientmod.TransactionFields.TRANSACTION
        for txn in paypal.iter_transactions(
                args.start_date, args.end_date, args.transaction_fields,
        ):
            summarize_transaction(txn, stdout)
    else:
        YAMLDumper.add_transaction_representer(args.transaction_fields)
        for paypal_id in args.paypal_ids:
            paypal_id = paypal_id.upper()
            paypal_obj: paypal_types.APIResponse
            if paypal_id.startswith('I-'):
                paypal_obj = paypal.get_subscription(paypal_id, fields=args.subscription_fields)
            else:
                paypal_obj = paypal.get_transaction(
                    paypal_id, args.end_date, args.start_date, args.transaction_fields,
                )
            yaml.dump(paypal_obj, stdout, Dumper=YAMLDumper)
    return 0

entry_point = cliutil.make_entry_point(__name__, PROGNAME)

if __name__ == '__main__':
    exit(entry_point())
