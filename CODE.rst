Code Overview
=============

This document gives a quick overview of the structure of the ``paypal_rest`` code.

``client.py`` is the heart of the library. This is the code that takes Python data, constructs a API request from it, sends it to PayPal, and then turns the result back into Python data.

There are separate modules to provide higher-level interfaces to those results. Right now there's just ``transaction.py``, which knows how to traverse the JSON result; convert data types like datetimes and amounts to native Python data structures; and so on.

Adding support for more of the API should follow this pattern: add method(s) to ``client.PayPalAPIClient``, and have them return rich data structures from a corresponding submodule.

The ``paypal-query`` tool is implemented in ``cliquery.py``. Other submodules like ``cliutil.py`` and ``config.py`` support it.

Running tests
-------------

Run ``pytest`` to run unit tests. Run ``mypy paypal_rest`` to run the type checker. Run ``tox`` to run both on all supported Pythons.
