#!/usr/bin/env python3
"""setup.py - paypal_rest installation script"""
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

from pathlib import Path
from setuptools import setup

README_PATH = Path(__file__).with_name('README.rst')

with README_PATH.open() as readme_file:
    long_description = readme_file.read()

setup(
    name='paypal_rest',
    version='1.0.0',
    author='Software Freedom Conservancy',
    author_email='info@sfconservancy.org',
    license='GNU AGPLv3+',
    url='https://k.sfconservancy.org/NPO-Accounting/paypal_rest',
    description="Library to access PayPal's REST API",
    long_description=long_description,

    python_requires='>=3.6',
    install_requires=[
        'iso8601>=0.1',  # Debian:python3-iso8601
        'oauthlib>=2.0',  # Debian:python3-oauthlib
        'pyxdg>=0.2',  # Debian:python3-xdg
        'requests>=2.0',  # Debian:python3-requests
        'requests-oauthlib>=1.0',  # Debian:python3-requests-oauthlib
    ],
    setup_requires=[
        'pytest-mypy',
        'pytest-runner',  # Debian:python3-pytest-runner
    ],
    tests_require=[
        'mypy>=0.770',  # Debian:python3-mypy
        'pytest',  # Debian:python3-pytest
    ],

    packages=[
        'paypal_rest',
    ],
    entry_points={
        'console_scripts': [
            'paypal-query = paypal_rest.cliquery:entry_point',
        ],
    },
)
