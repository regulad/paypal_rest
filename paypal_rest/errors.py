"""errors.py - PayPal API client exception classes"""
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

class MissingFieldError(KeyError):
    """Error raised when code tries to access an unloaded field

    This error is raised by PayPal object classes when the caller tries to
    access a field that was not loaded in the original API call. For
    example, trying to get a payer's name or email address from a Transaction
    when the ``fields`` argument did not include ``TransactionFields.PAYER``.
    """
    pass
