#!/usr/bin/env python

# Copyright 2016 Amazon.com, Inc. or its affiliates.
# Additions by Jason Carter
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# or in the "license" file accompanying this file.
# This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.


from lib.config import *
import lib.const as CONST
import argparse
import logging

_LOGGER = logging.getLogger(__name__)

if __name__ == "__main__":
    # Setup Logging


    # Setup Command Line Parser
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', help='Config File to Process')
    parser.add_argument(
        '-d', '--debug',
        help="Print lots of debugging statements",
        action="store_const", dest="loglevel", const=logging.DEBUG,
        default=logging.WARNING,
    )
    parser.add_argument(
        '-v', '--verbose',
        help="Be verbose",
        action="store_const", dest="loglevel", const=logging.INFO,
    )
    args = parser.parse_args()

    try:
        c = Config(args.filename, level=args.loglevel)
    except Exception as e:
        raise ValueError(
            "Failed to parse the YAML Configuration file. "
            "Check your syntax and spacing!\n\n{}".format(e)
        )

    try:
        c.load(CONST.TO_YAML)
    except Exception as e:
        raise ValueError(
            "Failed to parse the YAML Configuration file. "
            "Check your syntax and spacing!\n\n{}".format(e)
        )
