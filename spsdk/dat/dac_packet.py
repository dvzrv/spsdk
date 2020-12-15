#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2020 NXP
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module with Debug Authentication Challenge (DAC) Packet."""

from struct import unpack_from, pack, calcsize


class DebugAuthenticationChallenge:
    """Base class for DebugAuthenticationChallenge."""

    def __init__(self, version: str, socc: int, uuid: bytes, rotid_rkh_revocation: int,
                 rotid_rkth_hash: bytes, cc_soc_pinned: int, cc_soc_default: int,
                 cc_vu: int, challenge: bytes) -> None:
        """Initialize the DebugAuthenticationChallenge object.

        :param version: The string representing version: for RSA: 1.0, for ECC: 2.0, 2.1, 2.2
        :param socc: The SoC Class that this credential applies to
        :param uuid: The string representing the unique device identifier
        :param rotid_rkh_revocation: State of certificate revocation field
        :param rotid_rkth_hash: The hash of roth-meta data
        :param cc_soc_pinned: State of lock bits in the debugger configuration field
        :param cc_soc_default: State of the debugger configuration field
        :param cc_vu: The Vendor usage that the vendor has associated with this credential
        :param challenge: Randomly generated bytes from the target
        """
        self.version = version
        self.socc = socc
        self.uuid = uuid
        self.rotid_rkh_revocation = rotid_rkh_revocation
        self.rotid_rkth_hash = rotid_rkth_hash
        self.cc_soc_pinned = cc_soc_pinned
        self.cc_soc_default = cc_soc_default
        self.cc_vu = cc_vu
        self.challenge = challenge

    def info(self) -> str:
        """String representation of DebugCredential."""
        msg = f"Version                : {self.version}\n"  # pylint: disable=bad-whitespace
        msg += f"SOCC                   : {self.socc}\n"
        msg += f"UUID                   : {self.uuid.hex().upper()}\n"
        msg += f"CC_VU                  : {self.cc_vu}\n"
        msg += f"ROTID_rkh_revocation   : {format(self.rotid_rkh_revocation, '08X')}\n"
        msg += f"ROTID_rkth_hash        : {self.rotid_rkth_hash.hex()}\n"
        msg += f"CC_soc_pinned          : {format(self.cc_soc_pinned, '08X')}\n"
        msg += f"CC_soc_default         : {format(self.cc_soc_default, '08X')}\n"
        msg += f"Challenge              : {self.challenge.hex()}\n"
        return msg

    def export(self) -> bytes:
        """Exports the DebugAuthenticationChallenge into bytes."""
        data = pack("<2H", *[int(part) for part in self.version.split('.')])
        data += pack("<L", self.socc)
        data += self.uuid
        data += pack("<L", self.rotid_rkh_revocation)
        data += self.rotid_rkth_hash
        data += pack("<L", self.cc_soc_pinned)
        data += pack("<L", self.cc_soc_default)
        data += pack("<L", self.cc_vu)
        data += self.challenge
        return data

    @classmethod
    def parse(cls, data: bytes, offset: int = 0) -> 'DebugAuthenticationChallenge':
        """Parse the data into a DebugAuthenticationChallenge.

        :param data: Raw data as bytes
        :param offset: Offset within the input data
        :return: DebugAuthenticationChallenge object
        """
        format_head = '<2HL16sL'
        version_major, version_minor, socc, uuid, rotid_rkh_revocation = unpack_from(format_head, data, offset)
        hash_length = 48 if (socc == 4 and version_minor == 1 and version_major == 2) else 32
        format_tail = f'<{hash_length}s3L32s'
        (
            rotid_rkth_hash, cc_soc_pinned, cc_soc_default, cc_vu, challenge
        ) = unpack_from(format_tail, data, offset + calcsize(format_head))
        return cls(version=f'{version_major}.{version_minor}', socc=socc, uuid=uuid,
                   rotid_rkh_revocation=rotid_rkh_revocation, rotid_rkth_hash=rotid_rkth_hash,
                   cc_soc_default=cc_soc_default, cc_soc_pinned=cc_soc_pinned, cc_vu=cc_vu,
                   challenge=challenge)