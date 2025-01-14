#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2019-2021 NXP
#
# SPDX-License-Identifier: BSD-3-Clause
"""File including constants."""

from spsdk.utils.easy_enum import Enum


########################################################################################################################
# Enums version 3.1
########################################################################################################################
class EnumCmdTag(Enum):
    """Contains commands tags."""

    NONE = (0x00, "NONE")
    ERASE = (0x01, "ERASE")
    LOAD = (0x02, "LOAD")
    EXECUTE = (0x03, "EXECUTE")
    CALL = (0x04, "CALL")
    PROGRAM_FUSES = (0x05, "PROGRAM_FUSES")
    PROGRAM_IFR = (0x06, "PROGRAM_IFR")
    LOAD_CMAC = (0x07, "LOAD_CMAC")
    COPY = (0x08, "COPY")
    LOAD_HASH_LOCKING = (0x09, "LOAD_HASH_LOCKING")
    LOAD_KEY_BLOB = (0x0A, "LOAD_KEY_BLOB")
    CONFIGURE_MEMORY = (0x0B, "CONFIGURE_MEMORY")
    FILL_MEMORY = (0x0C, "FILL_MEMORY")
    FW_VERSION_CHECK = (0x0D, "FW_VERSION_CHECK")
