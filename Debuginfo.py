#!/usr/bin/env python

# MIT License

# Copyright (c) 2024 Luca Rufer

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import inspect
import json
import os
import typing
import struct
from abc import ABC, abstractmethod
from functools import reduce
from typing import Any, Generator, Type, TypeVar, Union

JSONVal = Union[None, bool, str, float, int, 'JSONArray', 'JSONObject']
JSONArray = list[JSONVal]
JSONObject = dict[str, JSONVal]

ConvertibleValue = Union[None, bool, str, float, int, 'ConvertibleArray', 'ConvertibleObject']
ConvertibleObject = dict[Union[str, 'DebugInfo.Member'], ConvertibleValue]
ConvertibleArray = list[ConvertibleValue]

class DebugInfo:

  class ParsableEntry(ABC):
    @abstractmethod
    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      pass    

  class DebugInfoEntry(ParsableEntry):
    @classmethod
    @abstractmethod
    def get_datatype(cls) -> str:
      pass

    @abstractmethod
    def __init__(self):
      self.name: str|None
      self.datawidth: int|None
      self.commentBefore: str|None
      self.commentAfter: str|None
      self.comment: str|None
      self.declaration_file: str|None
      self.declaration_line: int|None
      self.declaration_column: int|None

    @abstractmethod
    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      self.name = parser.parse_optional_attribute(self, info, 'name', str)
      self.datawidth = parser.parse_optional_attribute(self, info, 'datawidth', int)
      self.commentBefore = parser.parse_optional_attribute(self, info, 'commentBefore', str)
      self.commentAfter = parser.parse_optional_attribute(self, info, 'commentAfter', str)
      self.comment = parser.parse_optional_attribute(self, info, 'comment', str)
      self.declaration_file = parser.parse_optional_attribute(self, info, 'declaration_file', str)
      self.declaration_line = parser.parse_optional_attribute(self, info, 'declaration_line', int)
      self.declaration_column = parser.parse_optional_attribute(self, info, 'declaration_column', int)

    @abstractmethod
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      pass

    def get_datawidth(self) -> int|None:
      return self.datawidth

  class Base(DebugInfoEntry):
    def __init__(self):
      super().__init__()

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser)

  class Void(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "void"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      if value is None:
        return bytes(0)
      raise ValueError(value)

  class Boolean(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "boolean"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None
      if datawidth == 0: return bytes(0)

      bool_value: bool
      if value is None:
        bool_value = False
      elif type(value) is int: 
        bool_value = (value != 0)
      elif type(value) is float:
        bool_value = (value != 0.0)
      elif type(value) is bool:
        bool_value = value
      elif type(value) is str:
        if value.lower() in ["true", "yes", "1"]:
          bool_value = True
        elif value.lower() in ["false", "no", "0"]:
          bool_value = False
        else:
          raise ValueError(value) 
      else:
        raise ValueError(value)
      
      return (datawidth - 1) * b'\x00' + (b'\x01' if bool_value else b'\x00')

  class Char(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "char"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert self.get_datawidth() == 1

      if value is None:
        return b'\x00'
      elif type(value) is int:
        if value < -128 or value > 127:
          raise ValueError(value)
        if value < 0: value += 256
        return bytes([value])
      elif type(value) is bool:
        return b'\x01' if value else b'\x00'
      elif type(value) is float:
        raise ValueError(value)
      elif type(value) is str:
        # Empty value
        if len(value) == 0:
          return b'\x00'
        # Single character
        if len(value) == 1:
          return bytes(value, "ascii", 'strict')
        # Escaped single character
        escaped_characters = {"\\a": b"\a", "\\b": b"\b", "\\f": b"\f", "\\n": b"\n", 
                              "\\r": b"\r", "\\t": b"\t", "\\v": b"\v", "\\0": b"\0"}
        if value in escaped_characters:
          return escaped_characters[value]
        # Hex coding
        if len(value) == 4 and (value.startswith("0x") or value.startswith("\\x")):
          return bytes.fromhex(value[2:4])
        # Octal coding
        if len(value) == 4 and value.startswith("\\"):
          return bytes([int(value[1:4], 8)])
        # No match
        raise ValueError(value)
      else:
        raise ValueError(value)

  class UChar(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "uchar"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert self.get_datawidth() == 1

      if value is None:
        return b'\x00'
      elif type(value) is int:
        if value < 0 or value > 255:
          raise ValueError(value)
        return bytes([value])
      elif type(value) is bool:
        return b'\x01' if value else b'\x00'
      elif type(value) is float:
        raise ValueError(value)
      elif type(value) is str:
        # Empty value
        if len(value) == 0:
          return b'\x00'
        # Single character
        if len(value) == 1:
          return bytes(value, "ascii", 'strict')
        # Escaped single character
        escaped_characters = {"\\a": b"\a", "\\b": b"\b", "\\f": b"\f", "\\n": b"\n", 
                              "\\r": b"\r", "\\t": b"\t", "\\v": b"\v", "\\0": b"\0"}
        if value in escaped_characters:
          return escaped_characters[value]
        # Hex coding
        if len(value) == 4 and (value.startswith("0x") or value.startswith("\\x")):
          return bytes.fromhex(value[2:4])
        # Octal coding
        if len(value) == 4 and value.startswith("\\"):
          return bytes([int(value[1:4], 8)])
        # No match
        raise ValueError(value)
      else:
        raise ValueError(value)

  class Int(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "int"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None

      if value is None:
        value = 0
      elif type(value) is float:
        if value % 1 != 0:
          raise ValueError(value)
        value = int(value)
      elif type(value) is bool:
        value = 1 if value else 0
      elif type(value) is str:
        value = int(value, base=0)

      if type(value) is int:
        if value < self.lower_limit() or value > self.upper_limit():
          raise ValueError(value)
        return value.to_bytes(length=datawidth, byteorder='little', signed=True)
      else:
        raise ValueError(value)
      
    def lower_limit(self) -> int:
      assert (datawidth := self.get_datawidth()) is not None
      return -(1 << (datawidth * 8 - 1))
    
    def upper_limit(self) -> int:
      assert (datawidth := self.get_datawidth()) is not None
      return (1 << (datawidth * 8 - 1)) - 1

  class UInt(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "uint"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None

      if value is None:
        value = 0
      elif type(value) is float:
        if value % 1 != 0:
          raise ValueError(value)
        value = int(value)
      elif type(value) is bool:
        value = 1 if value else 0
      elif type(value) is str:
        value = int(value, base=0)

      if type(value) is int:
        if value < self.lower_limit() or value > self.upper_limit():
          raise ValueError(value)
        return value.to_bytes(length=datawidth, byteorder='little', signed=False)
      else:
        raise ValueError(value)
    
    def lower_limit(self) -> int:
      return 0
    
    def upper_limit(self) -> int:
      assert (datawidth := self.get_datawidth()) is not None
      return (1 << (datawidth * 8)) - 1

  class Float(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "float"
    
    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser)
      assert self.datawidth in [4, 8], "Float type must be either 4 Bytes (Float) or 8 Bytes (double) wide."

    def to_bytes(self, value: ConvertibleValue) -> bytes:
      if (datawidth := self.get_datawidth()) is None:
        raise ValueError(f"Cannot convert to float with unspecified datawidth")
      
      if value is None:
        value = 0.0
      if type(value) is int or type(value) is str or type(value) is bool:
        value = float(value)
      if not type(value) is float:
        raise ValueError(value)

      if datawidth == 4:
        return struct.pack("<f", value)
      elif datawidth == 8:
        return struct.pack("<d", value)
      else:
        raise ValueError(f"Unsupported datawidth: {datawidth}")

  class Address(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "address"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None

      if value is None:
        value = 0
      if type(value) is str:
        value = int(value, base=0)

      if type(value) is int:
        if value < self.lower_limit() or value > self.upper_limit():
          raise ValueError(value)
        return value.to_bytes(length=datawidth, byteorder='little', signed=False)
      else:
        raise ValueError(value)
    
    def lower_limit(self) -> int:
      return 0
    
    def upper_limit(self) -> int:
      assert (datawidth := self.get_datawidth()) is not None
      return (1 << (datawidth * 8)) - 1

  class ComplexFloat(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "complex float"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class ImaginaryFloat(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "imaginary float"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class PackedDecimal(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "packed decimal"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class NumericalString(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "numerical string"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class Edited(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "edited"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class Fixed(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "fixed"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class UFixed(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "ufixed"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class DecimalFloat(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "decimal float"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class UTF(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "UTF"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class UCS(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "UCS"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class ASCII(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "ASCII"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class Unknown(Base):
    @classmethod
    def get_datatype(cls) -> str:
      return "Unknown"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class Unspecified(DebugInfoEntry):
    @classmethod
    def get_datatype(cls) -> str:
      return "unspecified"

    def __init__(self):
      super().__init__()

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser)

    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class Typedef(DebugInfoEntry):
    @classmethod
    def get_datatype(cls) -> str:
      return "typedef"
    
    def __init__(self):
      super().__init__()
      self.type: DebugInfo.DebugInfoEntry

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser)
      self.name = parser.parse_attribute(self, info, 'name', str)
      self.type = parser.parse_type_attribute(self, info)

    def get_datawidth(self) -> int | None:
      if super().get_datawidth() is not None:
        return super().get_datawidth()
      elif self.type is not None:
        return self.type.get_datawidth()
      return None 
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      return self.type.to_bytes(value)
    
  class AbstractClassUnionStructure(DebugInfoEntry):
    def __init__(self):
      super().__init__()
      self.members: list[DebugInfo.Member]

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser)
      self.members = typing.cast(list[DebugInfo.Member], 
                                 parser.parse_list_attribute_as(self, info, 'members', DebugInfo.Member))
      
    def get_datawidth(self) -> int | None:
      if super().get_datawidth() is not None:
        return super().get_datawidth()
      max_member_width = 0
      for member in self.members:
        member_data_width = member.get_datawidth()
        if member.byte_offset is None or member_data_width is None:
          return None
        max_member_width = max(max_member_width, member.byte_offset + member_data_width)
      return max_member_width

  class Structure(AbstractClassUnionStructure):
    @classmethod
    def get_datatype(cls) -> str:
      return "struct"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None
      converted_bytes = bytearray(datawidth)
      if isinstance(value, dict):
        for member in self.members:
          member_candidates = [k for k in value 
                               if (isinstance(k, DebugInfo.Member) and k is member) or 
                                  (isinstance(k, str) and k == member.identifier)]
          if len(member_candidates) == 0:
            raise ValueError(f"Missing Value for Member {member.identifier} in {value}")
          elif len(member_candidates) > 1:
            raise ValueError(f"Multiple matches for Member {member.identifier}: {member_candidates}")
          member_value = value[member_candidates[0]]

          if member.type is None:
            raise ValueError(f"Cannot convert value to bytes for Member {member.identifier} with unknown type")
          if (member_width := member.get_datawidth()) is None:
            raise ValueError(f"Cannot convert value to bytes for Member {member.identifier} with unknown size")
          if member.byte_offset is None:
            raise ValueError(f"Cannot convert value to bytes for Member {member.identifier} with unknown offset")
          member_bytes = member.type.to_bytes(member_value)
          assert len(member_bytes) == member_width
          converted_bytes[member.byte_offset:member.byte_offset+member_width] = member_bytes    
        return converted_bytes
      else:
        raise ValueError(value)

  class Union(AbstractClassUnionStructure):
    @classmethod
    def get_datatype(cls) -> str:
      return "union"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None
      converted_bytes = bytearray(datawidth)
      if isinstance(value, dict):
        if len(value) != 1:
          raise ValueError(f"Only one member may be stated for a union: {value}")
        key, member_value = next(iter(value.items()))
        if isinstance(key, str):
          members = [m for m in self.members if m.identifier is not None and m.identifier == key]
          if len(members) == 0:
            raise ValueError(f"Member not found: {key}")
          member = members[0]
        elif key in self.members:
          member = key
        else:
          raise ValueError(f"Member not found: {key}")
      
        if member.type is None:
          raise ValueError(f"Cannot convert value to bytes for Member {member.identifier} with unknown type")
        if (member_width := member.get_datawidth()) is None:
          raise ValueError(f"Cannot convert value to bytes for Member {member.identifier} with unknown size")
        if member.byte_offset is None:
          raise ValueError(f"Cannot convert value to bytes for Member {member.identifier} with unknown offset")
        member_bytes = member.type.to_bytes(member_value)
        assert len(member_bytes) == member_width
        converted_bytes[member.byte_offset:member.byte_offset+member_width] = member_bytes    
        return converted_bytes
      else:
        raise ValueError(value)

  class Class(AbstractClassUnionStructure):
    @classmethod
    def get_datatype(cls) -> str:
      return "class"
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class Member(ParsableEntry):
    def __init__(self):
      super().__init__()
      self.identifier: str|None
      self.type: DebugInfo.DebugInfoEntry|None
      self.datawidth: int|None
      self.bitsize: int|None
      self.byte_offset: int|None
      self.bit_offset: int|None

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.identifier = parser.parse_optional_attribute(self, info, 'identifier', str)
      self.type = parser.parse_type_attribute(self, info)
      self.datawidth = parser.parse_optional_attribute(self, info, 'datawidth', int)
      self.bitsize = parser.parse_optional_attribute(self, info, 'bitsize', int)
      self.byte_offset = parser.parse_optional_attribute(self, info, 'byte_offset', int)
      self.bit_offset = parser.parse_optional_attribute(self, info, 'bit_offset', int)

    def get_datawidth(self) -> int | None:
      if self.datawidth is not None:
        return self.datawidth
      if self.type is not None:
        return self.type.get_datawidth()
      return None

  class Enumeration(DebugInfoEntry):
    @classmethod
    def get_datatype(cls) -> str:
      return "enumeration"
    
    def __init__(self):
      super().__init__()
      self.encoding: str|None
      self.type: DebugInfo.DebugInfoEntry|None
      self.enumerators: list[DebugInfo.Enumerator]

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.encoding = parser.parse_optional_attribute(self, info, 'encoding', str)
      self.type = parser.parse_optional_type_attribute(self, info, 'type')
      self.enumerators = typing.cast(list[DebugInfo.Enumerator],
                                     parser.parse_list_attribute_as(self, info, 'enumerators', DebugInfo.Enumerator))
      
    def get_datawidth(self) -> int | None:
      if super().get_datawidth() is not None:
        return super().get_datawidth()
      elif self.type is not None:
        return self.type.get_datawidth()
      return None 
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None

      if value is None:
        value = 0
      if isinstance(value, (int, str)):
        value_list = [value]
      elif isinstance(value, list):
        value_list = value
      else:
        raise ValueError(f"Enumeration value must be an integer, a string or a list of those, but is {value}")
      
      integer_value = 0
      for val in value_list:
        if isinstance(val, int):
          integer_value |= val
        elif isinstance(val, str):
          enumerators = [e for e in self.enumerators if e.representation == val]
          if len(enumerators) == 0:
            raise ValueError(f"Unknown enumerator '{val}'")
          integer_value |= enumerators[0].value
        else:
          raise ValueError(f"Enumeration value must be an integer, a string or a list of those, but is {value}")
        
      if self.type is not None:
        return self.type.to_bytes(integer_value)
      else:
        if integer_value < 0:
          integer_value += (1 << (datawidth * 8))
        return integer_value.to_bytes(datawidth, 'little')

  class Enumerator(ParsableEntry):
    def __init__(self):
      super().__init__()
      self.value: int
      self.representation: str

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.value = parser.parse_attribute(self, info, 'value', int)
      self.representation = parser.parse_attribute(self, info, 'representation', str)

  class Pointer(DebugInfoEntry):
    @classmethod
    def get_datatype(cls) -> str:
      return "pointer"
    
    def __init__(self):
      super().__init__()
      self.type: DebugInfo.DebugInfoEntry|None

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.type = parser.parse_optional_type_attribute(self, info)

    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None
      if value is None:
        value = 0
      if type(value) is str:
        value = int(value, base=0)
      if type(value) is int:
        if value < 0 or value >= (1 << (datawidth * 8)):
          raise ValueError(value)
        return value.to_bytes(length=datawidth, byteorder='little', signed=False)
      else:
        raise ValueError(value)

  class Reference(DebugInfoEntry):
    @classmethod
    def get_datatype(cls) -> str:
      return "reference"
    
    def __init__(self):
      super().__init__()
      self.type: DebugInfo.DebugInfoEntry|None

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.type = parser.parse_optional_type_attribute(self, info)

    def to_bytes(self, value: ConvertibleValue) -> bytes:
      assert (datawidth := self.get_datawidth()) is not None
      if value is None:
        value = 0
      if type(value) is str:
        value = int(value, base=0)
      if type(value) is int:
        if value < 0 or value >= (1 << (datawidth * 8)):
          raise ValueError(value)
        return value.to_bytes(length=datawidth, byteorder='little', signed=False)
      else:
        raise ValueError(value)

  class Array(DebugInfoEntry):
    @classmethod
    def get_datatype(cls) -> str:
      return "array"
    
    def __init__(self):
      super().__init__()
      self.dimensions: list[int]
      self.stride: int|None
      self.type: DebugInfo.DebugInfoEntry

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.dimensions = parser.parse_list_attribute(self, info, 'dimensions', int)
      self.stride = parser.parse_optional_attribute(self, info, 'stride', int)
      self.type = parser.parse_type_attribute(self, info)

    def get_stride(self) -> int | None:
      return self.stride if self.stride is not None else self.type.get_datawidth()
    
    def get_element_count(self) -> int:
      return reduce(lambda a, b: a * b, self.dimensions, 1)
    
    def get_element_width(self) -> int | None:
      return self.type.get_datawidth()

    def get_datawidth(self) -> int | None:
      if super().get_datawidth() is not None:
        return super().get_datawidth()
      if (stride := self.get_stride()) is not None:
        return stride * self.get_element_count()
      
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      return self._to_bytes(value)

    def _to_bytes(self, value: ConvertibleValue, dim_idx: int = 0) -> bytes:
      if dim_idx == len(self.dimensions):
        return self.type.to_bytes(value)
      if not isinstance(value, list):
        raise ValueError(f"Not a list: {value}")
      if len(value) != self.dimensions[dim_idx]:
        raise ValueError(f"Value must contain {self.dimensions[dim_idx]} elements, but contains {len(value)} elements")
      assert (stride := self.get_stride()) is not None
      bytes_ = bytearray(stride * reduce(lambda a, b: a * b, self.dimensions[dim_idx:], 1))
      for i in range(self.dimensions[dim_idx]):
        element_bytes = self._to_bytes(value[i], dim_idx + 1)
        bytes_[i*stride:i*stride+len(element_bytes)] = element_bytes
      return bytes_

  class Subroutine(DebugInfoEntry):
    @classmethod
    def get_datatype(cls) -> str:
      return "subroutine"
    
    def __init__(self):
      super().__init__()
      self.type: DebugInfo.DebugInfoEntry|None
      self.parameters: list[DebugInfo.Parameter]

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.type = parser.parse_optional_type_attribute(self, info, 'type')
      self.parameters = typing.cast(list[DebugInfo.Parameter], 
                                    parser.parse_list_attribute_as(self, info, 'parameters', DebugInfo.Parameter))
      
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      raise NotImplementedError()

  class Parameter(ParsableEntry):
    def __init__(self):
      super().__init__()
      self.name: str|None
      self.type: DebugInfo.DebugInfoEntry|None

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.name = parser.parse_optional_attribute(self, info, 'name', str)
      self.type = parser.parse_optional_type_attribute(self, info, 'type')

  class Variable(DebugInfoEntry):
    @classmethod
    def get_datatype(cls) -> str:
      return "variable"
    
    def __init__(self):
      super().__init__()
      self.type: DebugInfo.DebugInfoEntry|None
      self.location: int|None
      self.physical_location: int|None

    def parse(self, info: JSONObject, parser: DebugInfo.Parser) -> None:
      super().parse(info, parser) 
      self.type = parser.parse_optional_type_attribute(self, info, 'type')
      self.location = parser.parse_optional_attribute(self, info, 'location', int)
      self.physical_location = parser.parse_optional_attribute(self, info, 'physical_location', int)

    def get_datawidth(self) -> int | None:
      if super().get_datawidth() is not None:
        return super().get_datawidth()
      elif self.type is not None:
        return self.type.get_datawidth()
      return None
    
    def to_bytes(self, value: ConvertibleValue) -> bytes:
      if self.type is None:
        raise ValueError()
      return self.type.to_bytes(value)

  ParsableEntryType = TypeVar('ParsableEntryType', bound=ParsableEntry)
  DebugInfoEntryType = TypeVar('DebugInfoEntryType', bound=DebugInfoEntry)

  class Parser:
    FundamentalType = TypeVar('FundamentalType', None, bool, str, float, int)

    def __init__(self, debugInfo: DebugInfo, datatype_map: dict[str, type[DebugInfo.DebugInfoEntry]]) -> None:
      self.debugInfo = debugInfo
      self.datatype_map = datatype_map

    def get_datatype(self, info: JSONObject) -> type[DebugInfo.DebugInfoEntry]:
      assert 'datatype' in info, f"definition must have a 'datatype': {info}"
      assert isinstance(datatype := info['datatype'], str), f"'datatype' must be a string: {datatype}"
      assert datatype in self.datatype_map, f"'{datatype}' is not a supported datatype. Must be any of {self.datatype_map.keys()}"
      return self.datatype_map[datatype]
    
    def get_name(self, info: JSONObject) -> str|None:
      if not 'name' in info:
        return None
      assert isinstance(name := info['name'], str), f"'name' must be a string: {name}"
      return name
  
    def parse_attribute(self, 
                        entry: DebugInfo.ParsableEntry,
                        info: JSONObject, 
                        attribute: str, 
                        attribute_type: Type[FundamentalType]|tuple[Type[FundamentalType], ...]) -> FundamentalType:
      cls_name = entry.__class__.__name__
      assert attribute in info, \
        f"[DebugInfo] Entry of type {cls_name} must contain attribute '{attribute}': {info}"
      assert isinstance(value := info[attribute], attribute_type), \
        f"[DebugInfo] Type {cls_name} entry '{attribute}' must be of type {attribute_type}, but is {value}"
      return value
  
    def parse_optional_attribute(self, 
                                 entry: DebugInfo.ParsableEntry,
                                 info: JSONObject, 
                                 attribute: str, 
                                 attribute_type: Type[FundamentalType]|tuple[Type[FundamentalType], ...]
                                ) -> FundamentalType|None:
      cls_name = entry.__class__.__name__
      if not attribute in info: 
        value = None
      else:
        assert isinstance(value := info[attribute], attribute_type), \
          f"[DebugInfo] Type {cls_name} entry '{attribute}' must be of type {attribute_type}, but is {value}"
      return value

    def parse_type_attribute(self, 
                             entry: DebugInfo.ParsableEntry,
                             info: JSONObject, 
                             attribute: str|tuple[str, ...] = ("type")) -> DebugInfo.DebugInfoEntryType:
      cls_name = entry.__class__.__name__
      if isinstance(attribute, str):
        attribute = (attribute,)
      attribute = tuple([attr for attr in attribute if attr in info])
      value: DebugInfo.DebugInfoEntry|None = None
      for attr in attribute:
        attr_value = info[attr]
        if isinstance(attr_value, str):
          datatype = self.get_datatype(info)
          value = self.debugInfo.get_entry(datatype, attr_value)
        elif isinstance(attr_value, dict):
          value = self.debugInfo._parse_nested_entry(self, attr_value)
        else:
          raise Exception(f"Cannot parse attribute '{attr}' of {cls_name} as type")
        break
      else:
        value = self.debugInfo._parse_nested_entry(self, info)
      return value

    def parse_optional_type_attribute(self, 
                                      entry: DebugInfo.ParsableEntry,
                                      info: JSONObject, 
                                      attribute: str|tuple[str, ...] = ("type")) -> DebugInfo.DebugInfoEntryType|None:
      if isinstance(attribute, str):
        attribute = (attribute,)
      if any([attr in info for attr in attribute]):
        return self.parse_type_attribute(entry, info, attribute)
      else:
        return None

    def parse_list_attribute(self, 
                             entry: DebugInfo.ParsableEntry,
                             info: JSONObject, 
                             attribute: str, 
                             attribute_type: Type[FundamentalType]|tuple[Type[FundamentalType], ...]
                            ) -> list[FundamentalType]:
      cls_name = entry.__class__.__name__
      assert attribute in info, \
        f"[DebugInfo] Entry of type {cls_name} must contain attribute '{attribute}': {info}"
      assert isinstance(info_list := info[attribute], list), \
        f"[DebugInfo] Type {cls_name} entry '{attribute}' must be a list, but is {info_list}"
      parsed_obj_list = []
      for value in info_list:
        assert isinstance(value, attribute_type), \
          f"[DebugInfo] Type {cls_name} entry '{attribute}' must be {attribute_type}, but is {value}"
        parsed_obj_list.append(value)
      return parsed_obj_list

    def parse_list_attribute_as(self, 
                                entry: DebugInfo.ParsableEntry,
                                info: JSONObject, 
                                attribute: str, 
                                parse_as: Type[DebugInfo.ParsableEntryType]) -> list[DebugInfo.ParsableEntryType]:
      cls_name = entry.__class__.__name__
      assert attribute in info, \
        f"[DebugInfo] Entry of type {cls_name} must contain attribute '{attribute}': {info}"
      assert isinstance(info_list := info[attribute], list), \
        f"[DebugInfo] Type {cls_name} entry '{attribute}' must be a list, but is {info_list}"
      parsed_obj_list: list[DebugInfo.ParsableEntryType] = []
      for value in info_list:
        assert isinstance(value, dict), \
          f"[DebugInfo] Type {cls_name} entry '{attribute}' must be a JSON Object, but is {value}"
        value = typing.cast(JSONObject, value)
        new_obj = parse_as() # type: ignore
        new_obj.parse(value, self)
        parsed_obj_list.append(new_obj)
      return parsed_obj_list

  def __init__(self):
    # A list of all non-abstract DebugInfoEntry classes
    self._entry_class_list: list[type[DebugInfo.DebugInfoEntry]] = [
      cls_ for cls_ in self._get_subclasses_of_class(DebugInfo.DebugInfoEntry)
      if issubclass(cls_, DebugInfo.DebugInfoEntry) and not inspect.isabstract(cls_)
    ]
    # Map a datatype string to a DebugInfoEntry class
    self._datatype_map: dict[str, type[DebugInfo.DebugInfoEntry]] = {
      cls_.get_datatype(): cls_ for cls_ in self._entry_class_list
    }
    # A map containing all named parsed entries, organized first by class and then by name
    self._named_entry_map: dict[type[DebugInfo.DebugInfoEntry], dict[str, DebugInfo.DebugInfoEntry]] = {
      cls_: {} for cls_ in self._entry_class_list
    }
    # A map containing all unnamed parsed entries, organized by class, then put in a list
    self._unnamed_entry_map: dict[type[DebugInfo.DebugInfoEntry], list[DebugInfo.DebugInfoEntry]] = {
      cls_: [] for cls_ in self._entry_class_list
    }
    # Vars for active parsing
    self._parsing_info_json : Any|None = None
    self._parsing_entry_list : list[DebugInfo.DebugInfoEntry|None] = []
    # Other state variables
    self._info_path: str|None = None

  def parse(self, info_path: str) -> list[DebugInfoEntry]:
    self.parser: DebugInfo.Parser = DebugInfo.Parser(self, self._datatype_map)
    with open(info_path, 'r') as info_file:
      self._parsing_info_json = json.load(info_file)
      self._parsing_entry_list = [None] * len(self._parsing_info_json)
      for idx in range(len(self._parsing_info_json)):
        self._parse_root_entry(idx)
    return_values = [entry for entry in self._parsing_entry_list if entry]
    self._parsing_info_json = None
    self._parsing_entry_list = []
    self._info_path = info_path
    return return_values
    
  def get_entry(self, datatype: Type[DebugInfoEntryType], name: str) -> DebugInfoEntryType:
      # Check if the entry was already parsed
      name_map = self._named_entry_map[datatype]
      if name in name_map:
        return typing.cast(datatype, name_map[name])
      # Check if an ongoing entry matches the specifics
      if self._parsing_info_json is not None:
        for idx, info in enumerate(self._parsing_info_json):
          info_datatype = self.parser.get_datatype(info)
          info_name = self.parser.get_name(info)
          if (info_datatype == datatype and info_name == name):
            self._parse_root_entry(idx)
            parsed_entry = self._parsing_entry_list[idx]
            assert parsed_entry is not None
            return typing.cast(datatype, parsed_entry)
      raise Exception(f"No entry named '{name}' of datatype {datatype.__name__} was found.")
  
  def add_entry(self, entry: DebugInfoEntry) -> DebugInfoEntry|None:
    if entry.name is not None:
      entry_map = self._named_entry_map[entry.__class__]
      previous_entry = entry_map[entry.name] if (entry.name in entry_map) else None
      entry_map[entry.name] = entry
      return previous_entry
    else:
      entry_list = self._unnamed_entry_map[entry.__class__] 
      entry_list.append(entry)
      return None
    
  def remove_entry(self, entry: DebugInfoEntry) -> list[DebugInfoEntry]|None:
    if entry.name is not None:
      entry_map = self._named_entry_map[entry.__class__]
      return [entry_map.pop(entry.name)] if entry.name in entry_map else None
    else:
      entry_list = self._unnamed_entry_map[entry.__class__] 
      indexes = [idx for idx, e in enumerate(entry_list) if e == entry]
      indexes.reverse()
      return_value = [entry_list.pop(idx) for idx in indexes]
      return_value.reverse()
      return return_value

  def is_up_to_date(self, project_path: str):
    assert self._info_path is not None
    type_declaration_files = self._get_type_declaration_files(project_path)
    debuginfo_mtime = os.path.getmtime(self._info_path)
    return all([os.path.getmtime(file_path) <= debuginfo_mtime for file_path in type_declaration_files])

  def iter_all_entries(self) -> Generator[DebugInfoEntry, None, None]:
    for entry_class in self._entry_class_list:
      for entry in self.iter_class_entries(entry_class):
        yield entry
      
  def iter_class_entries(self, cls_: Type[DebugInfoEntryType]) ->  Generator[DebugInfoEntryType, None, None]:
    for named_entry in self._named_entry_map[cls_].values():
      yield typing.cast(cls_, named_entry)
    for unnamed_entry in self._unnamed_entry_map[cls_]:
      yield typing.cast(cls_, unnamed_entry)

  def _get_type_declaration_files(self, project_path: str) -> list[str]:
    type_declaration_files: set[str] = set()
    for entry in self.iter_all_entries():
      if entry.declaration_file is not None:
        type_declaration_files.add(entry.declaration_file)
    return [os.path.abspath(os.path.join(project_path, file_path)) for file_path in type_declaration_files]

  def _parse_root_entry(self, idx: int) -> None:
    assert self._parsing_info_json is not None
    info_json = self._parsing_info_json[idx]

    if self._parsing_entry_list[idx] is None:
      datatype = self.parser.get_datatype(info_json)
      new_entry = datatype()
      self._parsing_entry_list[idx] = new_entry
      new_entry.parse(info_json, self.parser)
      self.add_entry(new_entry)

  def _parse_nested_entry(self, parser: Parser, info_obj: JSONObject) -> DebugInfo.DebugInfoEntry:
    datatype = parser.get_datatype(info_obj)

    if 'mapping' in info_obj:
      assert isinstance(mapping_name := info_obj['mapping'], str), f"'mapping' must be a string: {mapping_name}"
      return self.get_entry(datatype, mapping_name)
    else:
      entry: DebugInfo.DebugInfoEntry = datatype()
      entry.parse(info_obj, parser)
      return entry

  @classmethod
  def _get_subclasses_of_class(cls, of_class: type) -> list[type]:
    subclasses = of_class.__subclasses__()
    all_subclasses = list(subclasses)
    for sc in subclasses:
      all_subclasses.extend(cls._get_subclasses_of_class(sc))
    return all_subclasses
