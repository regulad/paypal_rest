paypal_rest
===========

Introduction
------------

``paypal_rest`` is a library to wrap PayPal's REST interface. In late 2020, most Python libraries for the PayPal API are focused on charging customers. This library is focused on getting information about past charges and customers.

paypal-query tool
-----------------

This library includes a command line tool, ``paypal-query``, to quickly get information from the API; provide an illustration of using the library; and help with debugging. To use it, first write a configuration file ``~/.config/paypal_rest/config.ini`` with your REST API app credentials from PayPal::

  [query]
  client_id = ...
  client_secret = ...
  ; site can 'live', 'sandbox', or an API endpoint URL
  site = live

To see an overview of transactions over a time period::

  paypal-query [--begin DATETIME] [--end DATETIME]

Specify all datetimes in ISO8601 format: ``YYYY-MM-DDTHH:MM:SS``. You can stop at any divider and omit the rest. You can also add a timezone offset, like ``-04:00`` or ``+01:00``, or ``Z`` for UTC.

To see details of a specific transaction or subscription::

  paypal-query [--end DATETIME] PAYPALID1234ABCD0 [...]

The PayPal API does not let you look up an individual transaction by ID; you have to search through 30-day time windows. The tool will automatically search backwards through time to find your result, but specifying the latest date to search from with the ``--end`` option can speed up the search significantly.

Library quickstart
------------------

Create a ``paypal_rest.PayPalAPIClient`` using one of the classmethod constructors, then call its methods and handle the results::

  config = configparser.ConfigParser()
  config.read(os.path.expanduser('~/.config/paypal_rest/config.ini'))
  paypal = paypal_rest.PayPalAPIClient.from_config(config['query'])
  for txn in paypal.iter_transactions(start_date, end_date):
    ...  # txn is a paypal_rest.transaction.Transaction object you can query.

For more details, refer to the pydoc for ``paypal_rest.PayPalAPIClient`` and ``paypal_rest.transaction.Transaction``.
