"""config.py - Load user configuration for PayPal API client"""
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

import configparser

from pathlib import Path
from xdg import BaseDirectory  # type:ignore[import]

from typing import (
    Union,
)

CONFIG_PATH = Path('paypal_rest', 'config.ini')

def load_config(path: Union[Path, str, None]=None) -> configparser.ConfigParser:
    if path is None:
        path = BaseDirectory.load_first_config(str(CONFIG_PATH))
        if path is None:
            # This path doesn't exist, but we'll handle that case later.
            path = Path(BaseDirectory.xdg_config_home, CONFIG_PATH)
    config = configparser.ConfigParser()
    with open(path) as config_file:
        config.read_file(config_file)
    return config
