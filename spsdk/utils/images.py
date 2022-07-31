#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2022 NXP
#
# SPDX-License-Identifier: BSD-3-Clause
"""Module to keep additional utilities for binary images."""

import logging
import math
import os
import textwrap
from typing import TYPE_CHECKING, Any, Dict, List

import colorama

from spsdk import SPSDK_DATA_FOLDER
from spsdk.exceptions import SPSDKError, SPSDKOverlapError, SPSDKValueError
from spsdk.utils.crypto.common import crypto_backend
from spsdk.utils.misc import (
    find_file,
    format_value,
    load_binary,
    size_fmt,
    value_to_bytes,
    value_to_int,
    write_file,
)
from spsdk.utils.schema_validator import ConfigTemplate, ValidationSchemas

if TYPE_CHECKING:
    # bincopy will be loaded lazily as needed, this is just to satisfy type-hint checkers
    import bincopy

BINARY_SCH_FILE = os.path.join(SPSDK_DATA_FOLDER, "image", "sch_binary.yml")

logger = logging.getLogger(__name__)


class ColorPicker:
    """Simple class to get each time when ask different color from list."""

    COLORS = [
        colorama.Fore.LIGHTBLACK_EX,
        colorama.Fore.BLUE,
        colorama.Fore.GREEN,
        colorama.Fore.CYAN,
        colorama.Fore.YELLOW,
        colorama.Fore.MAGENTA,
        colorama.Fore.WHITE,
        colorama.Fore.LIGHTBLUE_EX,
        colorama.Fore.LIGHTCYAN_EX,
        colorama.Fore.LIGHTGREEN_EX,
        colorama.Fore.LIGHTMAGENTA_EX,
        colorama.Fore.LIGHTWHITE_EX,
        colorama.Fore.LIGHTYELLOW_EX,
    ]

    def __init__(self) -> None:
        """Constructor of ColorPicker."""
        self.index = len(self.COLORS)

    def get_color(self, unwanted_color: str = None) -> str:
        """Get new color from list.

        :param unwanted_color: Color that should be omitted.
        :return: Color
        """
        self.index += 1
        if self.index >= len(ColorPicker.COLORS):
            self.index = 0
        if unwanted_color and ColorPicker.COLORS[self.index] == unwanted_color:
            return self.get_color(unwanted_color)
        return ColorPicker.COLORS[self.index]


class BinaryPattern:
    """Binary pattern class.

    Supported patterns:
        - rand: Random Pattern
        - zeros: Filled with zeros
        - ones: Filled with all ones
        - inc: Filled with repeated numbers incremented by one 0-0xff
        - any kind of number, that will be repeated to fill up whole image.
          The format could be decimal, hexadecimal, bytes.
    """

    SPECIAL_PATTERNS = ["rand", "zeros", "ones", "inc"]

    def __init__(self, pattern: str) -> None:
        """Constructor of pattern class.

        :param pattern: Supported patterns:
                        - rand: Random Pattern
                        - zeros: Filled with zeros
                        - ones: Filled with all ones
                        - inc: Filled with repeated numbers incremented by one 0-0xff
                        - any kind of number, that will be repeated to fill up whole image.
                        The format could be decimal, hexadecimal, bytes.
        :raises SPSDKValueError: Unsupported pattern detected.
        """
        try:
            value_to_int(pattern)
        except SPSDKError:
            if not pattern in BinaryPattern.SPECIAL_PATTERNS:
                raise SPSDKValueError(  # pylint: disable=raise-missing-from
                    f"Unsupported input pattern{pattern}"
                )

        self._pattern = pattern

    def get_block(self, size: int) -> bytes:
        """Get block filled with pattern.

        :param size: Size of block to return.
        :return: Filled up block with specified pattern.
        """
        if self._pattern == "zeros":
            return bytes(size)

        if self._pattern == "ones":
            return bytes(b"\xff" * size)

        if self._pattern == "rand":
            return crypto_backend().random_bytes(size)

        if self._pattern == "inc":
            return bytes((x & 0xFF for x in range(size)))

        pattern = value_to_bytes(self._pattern)
        block = bytes(pattern * int((size / len(pattern))))
        return block[:size]

    @property
    def pattern(self) -> str:
        """Get the pattern.

        :return: Pattern in string representation.
        """
        try:
            return hex(value_to_int(self._pattern))
        except SPSDKError:
            return self._pattern

    @staticmethod
    def load_from_config(config: str) -> "BinaryPattern":
        """Load binary pattern from configuration.

        :param config: Configuration block with binary pattern.
        :return: Binary Pattern object.
        """
        return BinaryPattern(config)


class BinaryImage:
    """Binary Image class."""

    MINIMAL_DRAW_WIDTH = 30

    def __init__(
        self,
        name: str,
        size: int = 0,
        offset: int = 0,
        description: str = None,
        binary: bytes = None,
        pattern: BinaryPattern = None,
        parent: "BinaryImage" = None,
    ) -> None:
        """Binary Image class constructor.

        :param name: Name of Image.
        :param size: Image size.
        :param offset: Image offset in parent image, defaults to 0
        :param description: Text description of image, defaults to None
        :param binary: Optional binary content.
        :param pattern: Optional binary pattern.
        :param parent: Handle to parent object, defaults to None
        """
        self.name = name
        self.description = description
        self.offset = offset
        self._size = size
        self.binary = binary
        self.pattern = pattern
        self.parent = parent
        if parent:
            assert isinstance(parent, BinaryImage)
        self.sub_images: List["BinaryImage"] = []

    def add_image(self, image: "BinaryImage") -> None:
        """Add new sub image information.

        :param image: Image object.
        """
        image.parent = self
        for i, child in enumerate(self.sub_images):
            if image.offset < child.offset:
                self.sub_images.insert(i, image)
                return
        self.sub_images.append(image)

    @property
    def image_name(self) -> str:
        """Image name including all parents.

        :return: Full Image name
        """
        if self.parent:
            return self.parent.image_name + "=>" + self.name
        return self.name

    @property
    def absolute_address(self) -> int:
        """Image absolute address relative to base parent.

        :return: Absolute address relative to base parent
        """
        if self.parent:
            return self.parent.absolute_address + self.offset
        return self.offset

    def aligned_start(self, alignment: int = 4) -> int:
        """Returns aligned start address.

        :param alignment: The alignment value, defaults to 4.
        :returns: Floor alignment address.
        """
        return math.floor(self.absolute_address / alignment) * alignment

    def aligned_length(self, alignment: int = 4) -> int:
        """Returns aligned length for erasing purposes.

        :param alignment: The alignment value, defaults to 4.
        :returns: Ceil alignment length.
        """
        end_address = self.absolute_address + len(self)
        aligned_end = math.ceil(end_address / alignment) * alignment
        aligned_len = aligned_end - self.aligned_start(alignment)
        return aligned_len

    def info(self) -> str:
        """Provides information about image.

        :return: String information about Image.
        """
        size = len(self)
        ret = ""
        ret += f"Name:   {self.image_name}\n"
        ret += f"Starts: {hex(self.absolute_address)}\n"
        ret += f"Ends:   {hex(self.absolute_address+ size-1)}\n"
        ret += f"Size:   {size_fmt(size, use_kibibyte=False)}\n"
        if self.pattern:
            ret += f"Pattern:{self.pattern.pattern}\n"
        if self.description:
            ret += self.description + "\n"
        return ret

    def validate(self) -> None:
        """Validate if the images doesn't overlaps each other."""
        if self.offset < 0:
            raise SPSDKValueError(
                f"Image offset of {self.image_name} cannot be in negative numbers."
            )
        if len(self) <= 0:
            raise SPSDKValueError(
                f"Image size of {self.image_name} cannot be in negative numbers or zero."
            )
        for image in self.sub_images:
            image.validate()
            begin = image.offset
            end = begin + len(image) - 1
            # Check if it fits inside the parent image
            if end > len(self):
                raise SPSDKOverlapError(
                    f"The image {image.name} doesn't fit into {self.name} parent image."
                )
            # Check if it doesn't overlap any other sibling image
            for sibling in self.sub_images:
                if sibling != image:
                    sibling_begin = sibling.offset
                    sibling_end = sibling_begin + len(sibling) - 1
                    if end < sibling_begin or begin > sibling_end:
                        continue

                    raise SPSDKOverlapError(
                        f"The image overlap error:\n"
                        f"{image.info()}\n"
                        "overlaps the:\n"
                        f"{sibling.info()}\n"
                    )

    def get_min_draw_width(self, include_sub_images: bool = True) -> int:
        """Get minimal width of table for draw function.

        :param include_sub_images: Include also sub images into, defaults to True
        :return: Minimal width in characters.
        """
        widths = [
            self.MINIMAL_DRAW_WIDTH,
            len(f"+--0x0000_0000--{self.name}--+"),
            len(f"|Size: {size_fmt(len(self), False)}|"),
        ]
        if include_sub_images:
            for child in self.sub_images:
                widths.append(child.get_min_draw_width() + 2)  # +2 means add vertical borders
        return max(widths)

    def draw(self, include_sub_images: bool = True, width: int = 0, color: str = "") -> str:
        """Draw the image into the ASCII graphics.

        :param include_sub_images: Include also sub images into, defaults to True
        :param width: Fixed width of table, 0 means autosize.
        :param color: Color of this block, None means automatic color.
        :raises SPSDKValueError: In case of invalid width.
        :return: ASCII art representation of image.
        """
        # +--0x0000_0000--Title1---------------+
        # |            Size: 2048B             |
        # |           Description1             |
        # |       Description1 2nd line        |
        # |+--0x0000_0000--Title11------------+|
        # ||           Size: 512B             ||
        # ||           Description11          ||
        # ||       Description11 2nd line     ||
        # |+--0x0000_01FF---------------------+|
        # |                                    |
        # |+--0x0000_0210--Title12------------+|
        # ||           Size: 512B             ||
        # ||           Description12          ||
        # ||       Description12 2nd line     ||
        # |+--0x0000_041F---------------------+|
        # +--0x0000_07FF-----------------------+
        def _get_centered_line(text: str) -> str:
            text_len = len(text)
            spaces = width - text_len - 2
            assert spaces >= 0, "Binary Image Draw: Center line is longer than width"
            padding_l = int(spaces / 2)
            padding_r = int(spaces - padding_l)
            return color + f"|{' '*padding_l}{text}{' '*padding_r}|" + colorama.Fore.WHITE + "\n"

        def wrap_block(inner: str) -> str:
            wrapped_block = ""
            lines = inner.splitlines(keepends=False)
            for line in lines:
                wrapped_block += color + "|" + line + color + "|" + colorama.Fore.WHITE + "\n"
            return wrapped_block

        color_picker = ColorPicker()
        try:
            self.validate()
            color = color or color_picker.get_color()
        except SPSDKError:
            color = colorama.Fore.RED

        block = "" if self.parent else "\n"
        min_width = self.get_min_draw_width(include_sub_images)
        if not width and self.parent is None:
            width = min_width

        if width < min_width:
            raise SPSDKValueError(
                f"Binary Image Draw: Width is to short ({width} < minimal width: {min_width})"
            )

        # - Title line
        header = f"+--{format_value(self.offset, 32)}--{self.name}--"
        block += color + f"{header}{'-'*(width-len(header)-1)}+" + colorama.Fore.WHITE + "\n"
        # - Size
        block += _get_centered_line(f"Size: {size_fmt(len(self), False)}")
        # - Description
        if self.description:
            for line in textwrap.wrap(self.description, width=width - 2, fix_sentence_endings=True):
                block += _get_centered_line(line)
        # - Pattern
        if self.pattern:
            block += _get_centered_line(f"Pattern: {self.pattern.pattern}")
        # - Inner blocks
        if include_sub_images:
            next_free_space = 0
            for child in self.sub_images:
                # If the images doesn't comes one by one place empty line
                if child.offset != next_free_space:
                    block += _get_centered_line(
                        f"Gap: {size_fmt(child.offset-next_free_space, False)}"
                    )
                next_free_space = child.offset + len(child)
                inner_block = child.draw(
                    include_sub_images=include_sub_images,
                    width=width - 2,
                    color=color_picker.get_color(color),
                )
                block += wrap_block(inner_block)

        # - Closing line
        footer = f"+--{format_value(self.offset + len(self) - 1, 32)}--"
        block += color + f"{footer}{'-'*(width-len(footer)-1)}+" + colorama.Fore.WHITE + "\n"

        if self.parent is None:
            block += "\n" + colorama.Fore.RESET
        return block

    def update_offsets(self) -> None:
        """Update offsets from the sub images into main offset value begin offsets."""
        offsets = []
        for image in self.sub_images:
            offsets.append(image.offset)

        min_offset = min(offsets)
        for image in self.sub_images:
            image.offset -= min_offset
        self.offset += min_offset

    def __len__(self) -> int:
        """Get length of image.

        If internal member size is not set(is zero) the size is computed from sub images.
        :return: Size of image.
        """
        if self._size:
            return self._size
        max_size = len(self.binary) if self.binary else 0
        for image in self.sub_images:
            size = image.offset + len(image)
            max_size = max(size, max_size)
        return max_size

    def export(self) -> bytes:
        """Export represented binary image.

        :return: Byte array of binary image.
        """
        ret = bytearray(self.pattern.get_block(len(self))) if self.pattern else bytearray(len(self))
        if self.binary:
            ret[: len(self.binary)] = self.binary
        for image in self.sub_images:
            ret[image.offset : image.offset + len(image)] = image.export()[: len(image)]
        return ret

    @staticmethod
    def get_validation_schemas() -> List[Dict[str, Any]]:
        """Get validation schemas list to check a supported configuration.

        :return: Validation schemas.
        """
        return [ValidationSchemas.get_schema_file(BINARY_SCH_FILE)]

    @staticmethod
    def load_from_config(config: Dict[str, Any], search_paths: List[str] = None) -> "BinaryImage":
        """Converts the configuration option into an Binary Image object.

        :param config: Description of binary image.
        :param search_paths: List of paths where to search for the file, defaults to None
        :return: Initialized Binary Image.
        """
        name = config.get("name", "Base Image")
        size = config.get("size", 0)
        pattern = BinaryPattern(config["pattern"])
        ret = BinaryImage(name=name, size=size, pattern=pattern)
        regions = config.get("regions")
        if regions:
            for i, region in enumerate(regions):
                binary_file: Dict = region.get("binary_file")
                if binary_file:
                    binary = load_binary(binary_file["path"], search_paths=search_paths)
                    offset = binary_file["offset"]
                    name = binary_file.get("name", binary_file["path"])
                    ret.add_image(BinaryImage(name, len(binary), offset, binary=binary))
                binary_block: Dict = region.get("binary_block")
                if binary_block:
                    size = binary_block["size"]
                    offset = binary_block["offset"]
                    name = binary_block.get("name", f"Binary block(#{i})")
                    pattern = BinaryPattern(binary_block["pattern"])
                    ret.add_image(BinaryImage(name, size, offset, pattern=pattern))
        return ret

    def save_binary_image(
        self,
        path: str,
        file_format: str = "BIN",
    ) -> None:
        # pylint: disable=missing-param-doc
        """Save binary data file.

        :param path: Path to the file.
        :param file_format: Format of saved file ('BIN', 'HEX', 'S19'), defaults to 'BIN'.
        :raises SPSDKValueError: The file format is invalid.
        """
        file_format = file_format.upper()
        if file_format.upper() not in ("BIN", "HEX", "S19"):
            raise SPSDKValueError(f"Invalid input file format: {file_format}")

        if file_format == "BIN":
            write_file(self.export(), path, mode="wb")
            return

        def add_into_binary(bin_image: BinaryImage) -> None:
            if bin_image.pattern:
                bin_file.add_binary(
                    bin_image.pattern.get_block(len(bin_image)),
                    address=bin_image.absolute_address,
                    overwrite=True,
                )

            if bin_image.binary:
                bin_file.add_binary(
                    bin_image.binary, address=bin_image.absolute_address, overwrite=True
                )

            for sub_image in bin_image.sub_images:
                add_into_binary(sub_image)

        # import bincopy only if needed to save startup time
        import bincopy  # pylint: disable=import-outside-toplevel

        bin_file = bincopy.BinFile()
        add_into_binary(self)

        if file_format == "HEX":
            write_file(bin_file.as_ihex(), path)
            return

        # And final supported format is....... Yes, S record from MOTOROLA
        write_file(bin_file.as_srec(), path)

    @staticmethod
    def generate_config_template() -> str:
        """Generate configuration template.

        :return: Template to create binary merge..
        """
        return ConfigTemplate(
            "Binary Image Configuration template.",
            BinaryImage.get_validation_schemas(),
        ).export_to_yaml()

    @staticmethod
    def load_binary_image(
        path: str,
        name: str = None,
        size: int = 0,
        offset: int = 0,
        description: str = None,
        pattern: BinaryPattern = None,
        search_paths: List[str] = None,
    ) -> "BinaryImage":
        # pylint: disable=missing-param-doc
        r"""Load binary data file.

        :param path: Path to the file.
        :param name: Name of Image, defaults to file name.
        :param size: Image size, defaults to 0.
        :param offset: Image offset in parent image, defaults to 0
        :param description: Text description of image, defaults to None
        :param pattern: Optional binary pattern.
        :param search_paths: List of paths where to search for the file, defaults to None
        :raises SPSDKError: The binary file cannot be loaded.
        :return: Binary data represented in BinaryImage class.
        """
        path = find_file(path, search_paths=search_paths)
        try:
            with open(path, "rb") as f:
                data = f.read(4)
        except Exception as e:
            raise SPSDKError(f"Error loading file: {str(e)}") from e

        # import bincopy only if needed to save startup time
        import bincopy  # pylint: disable=import-outside-toplevel

        bin_file = bincopy.BinFile()
        try:
            if data == b"\x7fELF":
                logger.warning("Elf file support is experimental. Take that with care.")
                bin_file.add_elf_file(path)
            else:
                try:
                    bin_file.add_file(path)
                except (UnicodeDecodeError, bincopy.UnsupportedFileFormatError):
                    bin_file.add_binary_file(path)
        except Exception as e:
            raise SPSDKError(f"Error loading file: {str(e)}") from e

        img_name = name or os.path.basename(path)
        img_size = size or 0
        img_descr = description or f"The image loaded from: {path} ."
        bin_image = BinaryImage(
            name=img_name,
            size=img_size,
            offset=offset,
            description=img_descr,
            pattern=pattern,
        )
        if len(bin_file.segments) == 0:
            raise SPSDKError(f"Load of {path} failed, can't be decoded.")

        for i, segment in enumerate(bin_file.segments):
            bin_image.add_image(
                BinaryImage(
                    name=f"Segment {i}",
                    size=len(segment.data),
                    offset=segment.address,
                    pattern=pattern,
                    binary=segment.data,
                    parent=bin_image,
                )
            )
        # Optimize offsets in image
        bin_image.update_offsets()
        return bin_image