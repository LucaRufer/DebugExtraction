#!/usr/bin/env python

# MIT License

# Copyright (c) 2023 Luca Rufer

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

import posixpath
from abc import ABC, abstractmethod, abstractclassmethod
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from elftools.dwarf.compileunit import CompileUnit
import elftools.dwarf.constants as DWARFConstants
from elftools.dwarf.die import DIE
from typing import Any, Iterable
from io import BytesIO

class TypeParser:

  class Declaration:
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      pass

    def parse(self, die: DIE, parser: TypeParser, mandatory: bool = False):
      self.die = die
      self.file = parser.get_die_attribute_int(die, 'DW_AT_decl_file', mandatory=mandatory)
      self.line = parser.get_die_attribute_int(die, 'DW_AT_decl_line', mandatory=mandatory)
      self.column = parser.get_die_attribute_int(die, 'DW_AT_decl_column', mandatory=mandatory)
      self.file_name = self._get_file_name(die)

    def get_full_file_path(self) -> str|None:
      if self.file_name is None:
        return None
      compile_unit_die: DIE|None = self.die.cu.get_top_DIE()
      if compile_unit_die is None or compile_unit_die.tag != "DW_TAG_compile_unit":
        return None
      if (compile_dir_attr := compile_unit_die.attributes.get("DW_AT_comp_dir")) is None:
        return None
      compile_dir = compile_dir_attr.value.decode()
      full_path = posixpath.join(compile_dir, self.file_name)
      return full_path

    def _get_file_name(self, die: DIE) -> str|None:
      if self.file is None or self.file == 0:
        return None

      line_program = die.dwarfinfo.line_program_for_CU(die.cu)
      lp_header = line_program.header
      file_entry = lp_header["file_entry"][self.file - 1]

      dir_index = file_entry["dir_index"]
      if dir_index == 0:
        return file_entry.name.decode()

      directory = lp_header["include_directory"][dir_index - 1]
      return posixpath.join(directory, file_entry.name).decode()

    def __eq__(self, __value: TypeParser.Declaration) -> bool:
      if not isinstance(__value, TypeParser.Declaration):
        return NotImplemented
      # File number is ignored, as this may differ by CU
      return self.line == __value.line and \
             self.column == __value.column and \
             self.file_name == __value.file_name

    def __hash__(self) -> int:
      # File number is ignored, as this may differ by CU
      # File name is excluded for faster computation
      return hash((self.line, self.column))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      return f"Declaration({self.file}, {self.line}, {self.column})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      return f"File \"{self.file_name}\", Line: {self.line}, Column: {self.column}"

  class Accessible:
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      pass

    def parse(self, die: DIE, parser: TypeParser, mandatory: bool = False):
      self.accessibility = parser.get_die_attribute_int(die, 'DW_AT_accessibility', mandatory=mandatory)

    def is_public(self) -> bool:
      return self.accessibility == DWARFConstants.DW_ACCESS_public

    def is_private(self) -> bool:
      return self.accessibility == DWARFConstants.DW_ACCESS_private

    def is_protected(self) -> bool:
      return self.accessibility == DWARFConstants.DW_ACCESS_protected

    def __eq__(self, __value: TypeParser.Accessible) -> bool:
      if not isinstance(__value, TypeParser.Accessible):
        return NotImplemented
      return self.accessibility == __value.accessibility

    def __hash__(self) -> int:
      return hash(self.accessibility)

  class Aligned:
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      pass

    def parse(self, die: DIE, parser: TypeParser, mandatory: bool = False):
      self.alignment = parser.get_die_attribute_int(die, 'DW_AT_alignment', mandatory=mandatory)

    def align_on(self, address: int) -> int:
      if self.alignment is None:
        return address
      else:
        return (address + (self.alignment - 1)) // self.alignment * self.alignment

    def __eq__(self, __value: TypeParser.Aligned) -> bool:
      if not isinstance(__value, TypeParser.Aligned):
        return NotImplemented
      return self.alignment == __value.alignment

    def __hash__(self) -> int:
      return hash(self.alignment)

  class Artificial:
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      pass

    def parse(self, die: DIE, parser: TypeParser, mandatory: bool = False):
      self.artificial = parser.get_die_attribute_flag(die, 'DW_AT_artificial', default_value=False, mandatory=mandatory)

    def __eq__(self, __value: TypeParser.Artificial) -> bool:
      if not isinstance(__value, TypeParser.Artificial):
        return NotImplemented
      return self.artificial == __value.artificial

    def __hash__(self) -> int:
      return hash(self.artificial)

  class Declarable:
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      pass

    def parse(self, die: DIE, parser: TypeParser, mandatory: bool = False):
      self.declaration = parser.get_die_attribute_flag(die, 'DW_AT_declaration', default_value=False, mandatory=mandatory)

    def update_from(self, update: TypeParser.Declarable):
      assert(self.__class__ == update.__class__)
      update_attributes = [attr 
                           for attr in update.__dir__() 
                           if not attr.startswith("__") and 
                           self.__getattribute__(attr) is None and
                           update.__getattribute__(attr) is not None]
      for attr in update_attributes:
        self.__setattr__(attr, update.__getattribute__(attr))
      
      if isinstance(self, TypeParser.Typed) and "type" in update_attributes:
        self.type.add_referrer(self)

    def __eq__(self, __value: TypeParser.Declarable) -> bool:
      if not isinstance(__value, TypeParser.Declarable):
        return NotImplemented
      return self.declaration == __value.declaration

    def __hash__(self) -> int:
      return hash((self.declaration))

  class Named:
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      pass

    def parse(self, die: DIE, parser: TypeParser, mandatory: bool = False):
      self.name = parser.get_die_attribute_str(die, 'DW_AT_name', mandatory=mandatory)

    def get_name(self) -> str|None:
      return self.name

    def __eq__(self, __value: TypeParser.Named) -> bool:
      if not isinstance(__value, TypeParser.Named):
        return NotImplemented
      return self.name == __value.name

    def __hash__(self) -> int:
      return hash(self.name)

  class Sized:
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      pass

    def parse(self, die: DIE, parser: TypeParser, mandatory: bool = False):
      self.size = parser.get_die_attribute_int(die, 'DW_AT_byte_size')
      self.bit_size = parser.get_die_attribute_int(die, 'DW_AT_bit_size', mandatory=(mandatory and self.size is None))

    def byte_size(self) -> int|None:
      if self.size is not None:
        return self.size
      elif self.bit_size is not None:
        return (self.bit_size + 7) // 8
      else:
        return None

    def __eq__(self, __value: TypeParser.Sized) -> bool:
      if not isinstance(__value, TypeParser.Sized):
        return NotImplemented
      return self.size == __value.size and \
             self.bit_size == __value.bit_size

    def __hash__(self) -> int:
      return hash((self.size, self.bit_size))

  class Typed:
    TYPED_ATTR_NAMES = ["type"]
    def __init__(self) -> None:
      pass

    def parse(self, die: DIE, parser: TypeParser, mandatory: bool = False):
      self.type: TypeParser.AbstractTAG|None = parser.get_die_attribute_ref(die, 'DW_AT_type', mandatory=mandatory)
      if self.type is not None:
        self.type.add_referrer(self)

    def __eq__(self, __value: TypeParser.Typed) -> bool:
      if not isinstance(__value, TypeParser.Typed):
        return NotImplemented
      return self.type == __value.type

    def __hash__(self) -> int:
      return 0

  class AbstractTAG(ABC, Named):
    TYPED_ATTR_NAMES = ["_typedefs", "_referrers", "namespace"]
    @property
    @abstractmethod
    def DW_TAG(cls) -> str:
      pass

    @abstractmethod
    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      pass

    @abstractmethod
    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      pass

    def __init__(self) -> None:
      # Initialize attributes
      TypeParser.Named.__init__(self)
      self.decl = TypeParser.Declaration()
      # List of TAGs that use this TAG as it's type
      self._referrers: list[TypeParser.Typed] = []
      # Typedefs that reference this type. Only Typedef Types that were parsed are referenced
      self._typedefs: list[TypeParser.TypeDefType] = []
      # Namespace
      self.namespace: TypeParser.Namespace|None = None
      # Lazy dependency construction
      self._dependencies: list[TypeParser.AbstractTAG]|None = None
      self.parsed = False

    def parse(self, die: DIE, parser: TypeParser):
      # Assign DIE
      self.die = die
      self.decl.parse(die, parser)
      TypeParser.Named.parse(self, die, parser)
      # Parse Sibling for completeness, but don't store
      parser.get_die_attribute_ref_unparsed(die, "DW_AT_sibling")

    def parse_complete(self):
      self.parsed = True

    def deinit(self, replacement: TypeParser.AbstractTAG|None = None):
      # If a replacement is specified, make sure all TAGs that refer to this type are updated
      if replacement is not None:
        for referrer in self._referrers:
          if referrer.type is self:
            referrer.type = replacement
            replacement.add_referrer(referrer)
      # If this TAG is Typed, remove itself as a referrer to the type
      if isinstance(self, TypeParser.Typed) and self.type is not None:
        self.type.remove_referrer(self)

    def register_typedef(self, typedef: TypeParser.TypeDefType) -> None:
      if not typedef in self._typedefs:
        self._typedefs.append(typedef)

    def unregister_typedef(self, typedef: TypeParser.TypeDefType) -> None:
      remove_idxs = []
      for idx, registered_typedef in enumerate(self._typedefs):
        if typedef is registered_typedef:
          remove_idxs.append(idx)
      remove_idxs.reverse()
      for idx in remove_idxs:
        self._typedefs.pop(idx)

    def add_referrer(self, typed: TypeParser.Typed) -> None:
      self._referrers.append(typed)

    def remove_referrer(self, typed: TypeParser.Typed) -> None:
      remove_idxs = []
      for idx, referrer in enumerate(self._referrers):
        if typed is referrer:
          remove_idxs.append(idx)
      remove_idxs.reverse()
      for idx in remove_idxs:
        self._referrers.pop(idx)

    def set_namespace(self, namespace: TypeParser.Namespace) -> None:
      self.namespace = namespace

    def byte_size(self) -> int|None:
      if isinstance(self, TypeParser.Sized):
        if (sized_byte_size := TypeParser.Sized.byte_size(self)) is not None:
          return sized_byte_size
      if isinstance(self, TypeParser.Typed) and self.type is not None:
        return self.type.byte_size()
      return None

    def get_name(self) -> str|None:
      name = TypeParser.Named.get_name(self)
      # If no name was specified, return the name of a typedef, but only if it's unique
      if name is None:
        typedef_names = [t.name for t in self._typedefs if t.name is not None]
        if len(typedef_names) == 1:
          name = typedef_names[0]
      return name
    
    def get_scoped_name(self, separator: str) -> str|None:
      if self.namespace is None:
        return self.get_name()
      else:
        return self.namespace.get_scoped_name(separator) + separator + self.get_name()

    def get_tag_dependencies(self) -> list[TypeParser.AbstractTAG]:
      # Compute dependencies if not computed yet
      if self._dependencies is None:
        self._dependencies = []
        self._get_tag_dependencies(self._dependencies)
      return self._dependencies

    def _get_tag_dependencies(self, dependencies: list[TypeParser.AbstractTAG]) -> None:
      if not self in dependencies:
        dependencies.append(self)
        if isinstance(self, TypeParser.Typed) and self.type is not None:
          self.type._get_tag_dependencies(dependencies)

    def __eq__(self, __value: TypeParser.AbstractTAG) -> bool:
      if not isinstance(__value, TypeParser.AbstractTAG):
        return NotImplemented
      if not (self.parsed and __value.parsed):
        raise Exception("Cannot compare unparsed Abstract TAGs")
      return TypeParser.Named.__eq__(self, __value)

    def __hash__(self) -> int:
      return TypeParser.Named.__hash__(self)

  class AbstractType(AbstractTAG):
    TYPED_ATTR_NAMES = []

    def __init__(self) -> None:
      super().__init__()

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)

    def __eq__(self, __value: TypeParser.AbstractType) -> bool:
      if not isinstance(__value, TypeParser.AbstractType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.AbstractType.__bases__]) # type: ignore

    def __hash__(self) -> int:
      return hash(TypeParser.AbstractTAG.__hash__(self))

  class BaseType(AbstractType, Aligned, Sized):
    DW_TAG = 'DW_TAG_base_type'
    IGNORED_ATTRIBUTES = ['DW_AT_allocated', 'DW_AT_associated', 'DW_AT_binary_scale', 'DW_AT_data_location',
                          'DW_AT_decimal_scale', 'DW_AT_decimal_sign', 'DW_AT_digit_count', 'DW_AT_picture_string',
                          'DW_AT_small']
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)
      TypeParser.Sized.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser, mandatory=True)
      self.encoding = parser.get_die_attribute_int(die, 'DW_AT_encoding', mandatory=True)
      self.endianity = parser.get_die_attribute_int(die, 'DW_AT_endianity')
      self.bit_offset = parser.get_die_attribute_int(die, 'DW_AT_data_bit_offset', default_value=0, mandatory=(self.size is None))

    def __eq__(self, __value: TypeParser.BaseType) -> bool:
      if not isinstance(__value, TypeParser.BaseType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.BaseType.__bases__]) and \
             self.encoding == __value.encoding and \
             self.endianity == __value.endianity and \
             self.bit_offset == __value.bit_offset

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.BaseType.__bases__]),
                   self.encoding, self.endianity, self.bit_offset))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      return f"BaseType({self.name})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      return str(self.name)

  class UnspecifiedType(AbstractType):
    DW_TAG = 'DW_TAG_unspecified_type'
    IGNORED_ATTRIBUTES = []
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      super().__init__()

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Named.parse(self, die, parser, mandatory=True)

    def __eq__(self, __value: TypeParser.UnspecifiedType) -> bool:
      if not isinstance(__value, TypeParser.UnspecifiedType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.UnspecifiedType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.UnspecifiedType.__bases__])))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      return f"UnspecifiedType({self.name})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      return str(self.name)

  class TypeDefType(AbstractType, Accessible, Aligned, Declarable, Typed, Named):
    DW_TAG = 'DW_TAG_typedef'
    IGNORED_ATTRIBUTES = ['DW_AT_allocated', 'DW_AT_associated', 'DW_AT_data_location', 'DW_AT_start_scope',
                          'DW_AT_visibility']
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      super().__init__()
      TypeParser.Accessible.__init__(self)
      TypeParser.Aligned.__init__(self)
      TypeParser.Declarable.__init__(self)
      TypeParser.Typed.__init__(self)
      TypeParser.Named.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Accessible.parse(self, die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Declarable.parse(self, die, parser)
      TypeParser.Typed.parse(self, die, parser, mandatory=True)
      TypeParser.Named.parse(self, die, parser, mandatory=True)
      self.name: str
      self.type: TypeParser.AbstractTAG

    def parse_complete(self):
      super().parse_complete()
      # Only register self as typedef once parsing is complete
      self.type.register_typedef(self)

    def deinit(self, **kwargs):
      super().deinit(**kwargs)
      self.type.unregister_typedef(self)

    def __eq__(self, __value: TypeParser.TypeDefType) -> bool:
      if not isinstance(__value, TypeParser.TypeDefType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.TypeDefType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.TypeDefType.__bases__])))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"TypeDefType({self.name})"
      else:
        visited.append(self)
        return f"TypeDefType({self.name}, {self.type.__repr__(visited)})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"{self.name} -> {self.type.get_name()}"
      else:
        visited.append(self)
        return f"{self.name} -> {self.type.__str__(visited)}"

  class StructureUnionClassAbstractType(AbstractType, Accessible, Aligned, Declarable, Sized):
    IGNORED_ATTRIBUTES = ['DW_AT_allocated', 'DW_AT_associated', 'DW_AT_data_location', 'DW_AT_signature',
                          'DW_AT_start_scope', 'DW_AT_visibility']
    TYPED_ATTR_NAMES = ["containing_structure", "specification", "members"]
    @property
    @abstractclassmethod
    def BRIEF_STR() -> str:
      pass

    def __init__(self, containing_structure: TypeParser.StructureUnionClassAbstractType|None = None) -> None:
      super().__init__()
      TypeParser.Accessible.__init__(self)
      TypeParser.Aligned.__init__(self)
      TypeParser.Declarable.__init__(self)
      TypeParser.Sized.__init__(self)
      self.containing_structure = containing_structure
      self.exported_symbols: list[TypeParser.Member] = []

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Accessible.parse(self, die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Declarable.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser)
      self.export_symbols = parser.get_die_attribute_flag(die, 'DW_AT_export_symbols', default_value=False)
      self.specification = parser.get_die_attribute_ref(die, 'DW_AT_specification')
      self.calling_convention: int = parser.get_die_attribute_int(die, 'DW_AT_calling_convention',
                                                                  default_value=DWARFConstants.DW_CC_normal)
      self.linkage_name = parser.get_die_attribute_str(die, 'DW_AT_linkage_name')
      if self.linkage_name is None:
        # Support gcc/g++ extension
        self.linkage_name = parser.get_die_attribute_str(die, 'DW_AT_MIPS_linkage_name')

      if 'DW_AT_signature' in die.attributes:
        raise Exception("Signature not supported")

      # Parse Children
      self.members: list[TypeParser.Member] = [parser.parse_DIE(ch, containing_structure=self)
                                              for ch in die.iter_children()
                                              if ch.tag == TypeParser.Member.DW_TAG]

      # Export Symbols
      if self.export_symbols and self.containing_structure is not None:
        self.containing_structure.add_exported_symbols(self.members)

    def byte_size(self) -> int|None:
      if TypeParser.Sized.byte_size(self) is not None:
        return TypeParser.Sized.byte_size(self)
      elif self.specification is not None:
        return self.specification.byte_size()
      else:
        return None

    def _get_tag_dependencies(self, dependencies: list[TypeParser.AbstractTAG]) -> None:
      if not self in dependencies:
        dependencies.append(self)
        for m in self.members:
          m.type._get_tag_dependencies(dependencies)

    def get_name(self, default:str|None = None) -> str|None:
      name = self.name
      if name is None and self.specification is not None:
        name = self.specification.get_name()
      if name is None:
        name = super().get_name()
      if name is None:
        name = default
      return name

    def is_incomplete(self) -> bool:
      return self.declaration is not None and self.declaration and self.size is None

    def _compare_members(self, __value: TypeParser.StructureUnionClassAbstractType) -> bool:
      if len(self.members) != len(__value.members):
        return False
      for self_member, value_member in zip(self.members, __value.members):
        if not self_member.is_similar(value_member):
          return False
      return True

    def __eq__(self, __value: TypeParser.StructureUnionClassAbstractType, compare_containing_structure: bool = True) -> bool:
      if not isinstance(__value, TypeParser.StructureUnionClassAbstractType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.StructureUnionClassAbstractType.__bases__]) and \
             ((not compare_containing_structure) or self.containing_structure == __value.containing_structure) and \
             self._compare_members(__value) and \
             self.export_symbols == __value.export_symbols and \
             self.specification == __value.specification and \
             self.calling_convention == __value.calling_convention

    def __hash__(self) -> int:
      # Containing structure and specification are not hashed
      return hash((tuple([c.__hash__(self) for c in TypeParser.StructureUnionClassAbstractType.__bases__]),
                   self.export_symbols, self.calling_convention))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"{self.__class__.__name__}({self.get_name(default='')})"
      else:
        visited.append(self)
        member_list_repr = ", ".join([m.__repr__(visited) for m in self.members])
        return f"{self.__class__.__name__}({self.get_name(default='')}, [{member_list_repr}])"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"{self.BRIEF_STR} {self.get_name(default='')}"
      else:
        visited.append(self)
        repr = f"{self.BRIEF_STR} {self.get_name(default='')} {{"
        for mem in self.members:
          repr += "\n" + mem.__str__(visited)
        repr += "}"
        return repr

    def add_exported_symbols(self, symbols: list[TypeParser.Member]) -> None:
      self.exported_symbols.extend(symbols)

  class Member(AbstractTAG, Accessible, Aligned, Artificial, Declarable, Sized, Typed):
    DW_TAG = 'DW_TAG_member'
    IGNORED_ATTRIBUTES = ['DW_AT_visibility']
    TYPED_ATTR_NAMES = ["containing_structure"]
    def __init__(self, containing_structure: TypeParser.StructureUnionClassAbstractType) -> None:
      super().__init__()
      TypeParser.Accessible.__init__(self)
      TypeParser.Aligned.__init__(self)
      TypeParser.Artificial.__init__(self)
      TypeParser.Declarable.__init__(self)
      TypeParser.Sized.__init__(self)
      TypeParser.Typed.__init__(self)
      self.containing_structure = containing_structure

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Accessible.parse(self, die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Artificial.parse(self, die, parser)
      TypeParser.Declarable.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser)
      TypeParser.Typed.parse(self, die, parser, mandatory=True)
      self.type : TypeParser.AbstractTAG
      self.mutable = parser.get_die_attribute_flag(die, 'DW_AT_mutable')
      if die.get_parent().tag in ('DW_TAG_structure_type', 'DW_TAG_union_type', 'DW_TAG_class_type'):
        # Note: Location description for data_member_location not supported, only integer byte offset
        self.data_member_location = parser.get_die_attribute_block_or_int(die, 'DW_AT_data_member_location', default_value=0)
        self.data_bit_offset = parser.get_die_attribute_int(die, 'DW_AT_bit_offset', default_value=0) if self.data_member_location else 0
      else:
        self.data_member_location = 0
        self.data_bit_offset = 0

      # Non-standard attributes generated by gcc/g++ for c++17
      self.external = parser.get_die_attribute_flag(die, 'DW_AT_external')
      self.const_expr = parser.get_die_attribute_flag(die, 'DW_AT_const_expr')
      self.inline = parser.get_die_attribute_int(die, 'DW_AT_inline')

    def get_offset(self, dwarf_stack: list[int]|None = None) -> tuple[int, int]|None:
      # Make sure dwarf stack exists
      if dwarf_stack is None:
        dwarf_stack = [0]
      # compute byte offset
      if isinstance(self.data_member_location, int):
        # Simple integer byte offset
        byte_offset = self.data_member_location
      elif isinstance(self.data_member_location, list):
        # Location Expression. Only 'DW_OP_plus_uconst' is currently supported
        opcode = self.data_member_location[0]
        if opcode == 0x23:
          stack_top = dwarf_stack.pop()
          byte_offset = self.data_member_location[1] + stack_top
          dwarf_stack.append(byte_offset)
        else:
          raise Exception(f"Cannot compute member offset: Unknown exprloc operation {hex(opcode)}.")
      else:
        return None
      # compute bit offset
      bit_offset = self.data_bit_offset
      if bit_offset is None:
        bit_offset = 0
      # return both values
      return (byte_offset, bit_offset)


    def is_anonymous(self) -> bool:
      return self.name is None or len(self.name) == 0

    def is_similar(self, __value: TypeParser.Member) -> bool:
      """A non-recursive alternative to __eq__ that does not compare some parameters to prevent possible recursion"""
      return self.name == __value.name and \
             self.declaration == __value.declaration and \
             self.size == __value.size and \
             self.bit_size == __value.bit_size and \
             self.type.name == __value.type.name and \
             self.accessibility == __value.accessibility and \
             self.mutable == __value.mutable and \
             self.data_member_location == __value.data_member_location and \
             self.data_bit_offset == __value.data_bit_offset


    def __eq__(self, __value: TypeParser.Member, compare_containing_structure: bool = True) -> bool:
      if not isinstance(__value, TypeParser.Member):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.Member.__bases__]) and \
             ((not compare_containing_structure) or (self.containing_structure == __value.containing_structure)) and \
             self.accessibility == __value.accessibility and \
             self.mutable == __value.mutable and \
             self.data_member_location == __value.data_member_location and \
             self.data_bit_offset == __value.data_bit_offset

    def __hash__(self) -> int:
      data_member_location_hash = self.data_member_location
      if isinstance(self.data_member_location, list):
        data_member_location_hash = hash(tuple(self.data_member_location))
      return hash((tuple([c.__hash__(self) for c in TypeParser.Member.__bases__]),
                   self.accessibility, self.mutable, self.data_bit_offset, data_member_location_hash))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"Member({self.type.get_name()}, {self.name})"
      else:
        visited.append(self)
        return f"Member({self.type.__repr__(visited)}, {self.name})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"{self.type.get_name()} {self.name}"
      else:
        visited.append(self)
        return f"{self.type.__str__(visited)} {self.name}"

  class StructureType(StructureUnionClassAbstractType):
    DW_TAG = 'DW_TAG_structure_type'
    BRIEF_STR = 'struct'

    def __eq__(self, __value: TypeParser.StructureType) -> bool:
      if not isinstance(__value, TypeParser.StructureType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.StructureType.__bases__])

    def __hash__(self) -> int:
      return super().__hash__()

  class ClassType(StructureUnionClassAbstractType):
    DW_TAG = 'DW_TAG_class_type'
    BRIEF_STR = 'class'

    def __eq__(self, __value: TypeParser.ClassType) -> bool:
      if not isinstance(__value, TypeParser.ClassType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.ClassType.__bases__])

    def __hash__(self) -> int:
      return super().__hash__()

  class UnionType(StructureUnionClassAbstractType):
    DW_TAG = 'DW_TAG_union_type'
    BRIEF_STR = 'union'

    def __eq__(self, __value: TypeParser.UnionType) -> bool:
      if not isinstance(__value, TypeParser.UnionType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.UnionType.__bases__])

    def __hash__(self) -> int:
      return super().__hash__()

  class Enumerator(AbstractTAG, Named):
    DW_TAG = 'DW_TAG_enumerator'
    TYPED_ATTR_NAMES = ["containing_structure"]
    def __init__(self, containing_structure: TypeParser.EnumerationType) -> None:
      super().__init__()
      TypeParser.Named.__init__(self)
      self.containing_structure = containing_structure

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Named.parse(self, die, parser, mandatory=True)
      self.name: str
      self.value: int = parser.get_die_attribute_int(die, 'DW_AT_const_value', mandatory=True)

    def __eq__(self, __value: TypeParser.Enumerator) -> bool:
      if not isinstance(__value, TypeParser.Enumerator):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.Enumerator.__bases__]) and \
             self.value == __value.value

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.Enumerator.__bases__]), \
                   self.value))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      return f"Enumerator({self.name}, {self.value})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      return f"{self.name} = {self.value}"

  class EnumerationType(AbstractType, Accessible, Aligned, Declarable, Sized, Typed):
    DW_TAG = 'DW_TAG_enumeration_type'
    IGNORED_ATTRIBUTES = ['DW_AT_allocated', 'DW_AT_associated', 'DW_AT_data_location', 'DW_AT_signature',
                          'DW_AT_specification', 'DW_AT_start_scope', 'DW_AT_visibility']
    TYPED_ATTR_NAMES = ["enumerators"]
    def __init__(self) -> None:
      super().__init__()
      TypeParser.Accessible.__init__(self)
      TypeParser.Aligned.__init__(self)
      TypeParser.Declarable.__init__(self)
      TypeParser.Sized.__init__(self)
      TypeParser.Typed.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Accessible.parse(self, die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Declarable.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser)
      type_required = (self.size is None and self.bit_size is None) and not self.declaration
      TypeParser.Typed.parse(self, die, parser, mandatory=type_required)
      self.enum_class = parser.get_die_attribute_flag(die, 'DW_AT_enum_class', default_value=False)
      self.byte_stride = parser.get_die_attribute_int(die, 'DW_AT_byte_stride')
      self.bit_stride = parser.get_die_attribute_int(die, 'DW_AT_bit_stride')
      self.encoding = parser.get_die_attribute_int(die, 'DW_AT_encoding')
      self.linkage_name = parser.get_die_attribute_str(die, 'DW_AT_linkage_name')
      if self.linkage_name is None:
        # Support gcc/g++ extension
        self.linkage_name = parser.get_die_attribute_str(die, 'DW_AT_MIPS_linkage_name')

      self.enumerators = [parser.parse_DIE(ch, containing_structure=self)
                          for ch in die.iter_children()
                          if ch.tag == TypeParser.Enumerator.DW_TAG]

    def __eq__(self, __value: TypeParser.EnumerationType) -> bool:
      if not isinstance(__value, TypeParser.EnumerationType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.EnumerationType.__bases__]) and \
             self.enum_class == __value.enum_class and \
             self.byte_stride == __value.byte_stride and \
             self.bit_stride == __value.bit_stride and \
             self.enumerators == __value.enumerators

    def __hash__(self) -> int:
      # Enumerators are not included in the hash
      return hash((tuple([c.__hash__(self) for c in TypeParser.EnumerationType.__bases__]), \
                   self.enum_class, self.byte_stride, self.bit_size))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"EnumerationType({self.name})"
      else:
        visited.append(self)
        enumerators_repr = ", ".join([e.__repr__(visited) for e in self.enumerators])
        return f"EnumerationType({self.name}, {self.type.__repr__(visited)}, [{enumerators_repr}])"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      name_str = (self.get_name() + ' ' if self.get_name() is not None else '')
      if self in visited:
        return f"Enumeration {name_str}"
      else:
        visited.append(self)
        enumerators_str = "\n".join([e.__str__(visited) for e in self.enumerators])
        return f"Enumeration {name_str} (type = {self.type.__str__(visited)}) {{\n {enumerators_str}}}"

  class AbstractModifierType(AbstractType, Typed):
    TYPED_ATTR_NAMES = []
    @property
    @abstractclassmethod
    def MODIFIER_STR_LEFT() -> str:
      pass

    @property
    @abstractclassmethod
    def MODIFIER_STR_RIGHT() -> str:
      pass

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Typed.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Typed.parse(self, die, parser)

    def get_name(self) -> str | None:
      name = super().get_name()
      if name is None and self.type is not None:
        name = self.type.get_name()
      return name

    def __eq__(self, __value: TypeParser.AbstractModifierType) -> bool:
      if not isinstance(__value, TypeParser.AbstractModifierType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.AbstractModifierType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.AbstractModifierType.__bases__])))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      # Abstract modifiers will always be extended
      class_name = self.__class__.__name__
      type_repr = self.type.__repr__(visited) if self.type is not None else 'None'
      return class_name + '(' + type_repr + ')'

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      # Abstract modifiers will always be extended
      type_str = self.type.__str__(visited) if self.type is not None else 'void'
      left_str = self.MODIFIER_STR_LEFT + ' ' if self.MODIFIER_STR_LEFT is not None else ''
      right_str = ' ' + self.MODIFIER_STR_RIGHT if self.MODIFIER_STR_RIGHT is not None else ''
      return left_str + type_str + right_str

  class AtomicType(AbstractModifierType, Aligned):
    DW_TAG = 'DW_TAG_atomic_type'
    MODIFIER_STR_LEFT = 'atomic'
    MODIFIER_STR_RIGHT = None

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)

    def __eq__(self, __value: TypeParser.AtomicType) -> bool:
      if not isinstance(__value, TypeParser.AtomicType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.AtomicType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.AtomicType.__bases__])))

  class ConstType(AbstractModifierType, Aligned):
    DW_TAG = 'DW_TAG_const_type'
    MODIFIER_STR_LEFT = 'const'
    MODIFIER_STR_RIGHT = None

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)

    def __eq__(self, __value: TypeParser.ConstType) -> bool:
      if not isinstance(__value, TypeParser.ConstType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.ConstType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.ConstType.__bases__])))

  class ImmutableType(AbstractModifierType):
    DW_TAG = 'DW_TAG_immutable_type'
    MODIFIER_STR_LEFT = 'immutable'
    MODIFIER_STR_RIGHT = None

    def __eq__(self, __value: TypeParser.ImmutableType) -> bool:
      if not isinstance(__value, TypeParser.ImmutableType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.ImmutableType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.ImmutableType.__bases__])))

  class PackedType(AbstractModifierType, Aligned):
    DW_TAG = 'DW_TAG_packed_type'
    MODIFIER_STR_LEFT = 'packed'
    MODIFIER_STR_RIGHT = None

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)

    def __eq__(self, __value: TypeParser.PackedType) -> bool:
      if not isinstance(__value, TypeParser.PackedType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.PackedType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.PackedType.__bases__])))

  class PointerType(AbstractModifierType, Aligned, Sized):
    DW_TAG = 'DW_TAG_pointer_type'
    MODIFIER_STR_LEFT = '*'
    MODIFIER_STR_RIGHT = None

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)
      TypeParser.Sized.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser)
      self.address_class = parser.get_die_attribute_int(die, 'DW_AT_address_class')

    def __eq__(self, __value: TypeParser.PointerType) -> bool:
      if not isinstance(__value, TypeParser.PointerType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.PointerType.__bases__]) and \
             self.address_class == __value.address_class

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.PointerType.__bases__]), \
                   self.address_class))

    def byte_size(self) -> int:
      if TypeParser.Sized.byte_size(self) is not None:
        return TypeParser.Sized.byte_size(self)
      else:
        return self.die.cu.header.address_size

  class ReferenceType(AbstractModifierType, Aligned, Sized):
    DW_TAG = 'DW_TAG_reference_type'
    MODIFIER_STR_LEFT = 'reference'
    MODIFIER_STR_RIGHT = None

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)
      TypeParser.Sized.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser)
      self.address_class = parser.get_die_attribute_int(die, 'DW_AT_address_class')

    def __eq__(self, __value: TypeParser.ReferenceType) -> bool:
      if not isinstance(__value, TypeParser.ReferenceType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.ReferenceType.__bases__]) and \
             self.address_class == __value.address_class

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.ReferenceType.__bases__]), \
                   self.address_class))

    def byte_size(self) -> int:
      sized_size = TypeParser.Sized.byte_size(self)
      if sized_size is not None:
        return sized_size
      else:
        return self.die.cu.header.address_size

  class RestrictType(AbstractModifierType, Aligned):
    DW_TAG = 'DW_TAG_restrict_type'
    MODIFIER_STR_LEFT = 'restric'
    MODIFIER_STR_RIGHT = None

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)

    def __eq__(self, __value: TypeParser.RestrictType) -> bool:
      if not isinstance(__value, TypeParser.RestrictType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.RestrictType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.RestrictType.__bases__])))

  class RValueReferenceType(AbstractModifierType, Aligned, Sized):
    DW_TAG = 'DW_TAG_rvalue_reference_type'
    MODIFIER_STR_LEFT = 'rvaluereference'
    MODIFIER_STR_RIGHT = None

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)
      TypeParser.Sized.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser)
      self.address_class = parser.get_die_attribute_int(die, 'DW_AT_address_class')

    def __eq__(self, __value: TypeParser.RValueReferenceType) -> bool:
      if not isinstance(__value, TypeParser.RValueReferenceType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.RValueReferenceType.__bases__]) and \
             self.address_class == __value.address_class

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.RValueReferenceType.__bases__]), \
                   self.address_class))

  class SharedType(AbstractModifierType, Aligned):
    DW_TAG = 'DW_TAG_shared_type'
    MODIFIER_STR_LEFT = 'shared'
    MODIFIER_STR_RIGHT = None

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Aligned.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      self.blocksize = parser.get_die_attribute_int(die, 'DW_AT_count')

    def __eq__(self, __value: TypeParser.SharedType) -> bool:
      if not isinstance(__value, TypeParser.SharedType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.SharedType.__bases__]) and \
             self.blocksize == __value.blocksize

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.SharedType.__bases__]), \
                   self.blocksize))

  class VolatileType(AbstractModifierType):
    DW_TAG = 'DW_TAG_volatile_type'
    MODIFIER_STR_LEFT = 'volatile'
    MODIFIER_STR_RIGHT = None

    def __eq__(self, __value: TypeParser.VolatileType) -> bool:
      if not isinstance(__value, TypeParser.VolatileType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.VolatileType.__bases__])

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.VolatileType.__bases__])))

  class Subrange(AbstractTAG, Accessible, Aligned, Declarable, Sized, Typed):
    DW_TAG = 'DW_TAG_subrange_type'
    IGNORED_ATTRIBUTES = ['DW_AT_allocated', 'DW_AT_associated', 'DW_AT_data_location', 'DW_AT_threads_scaled',
                          'DW_AT_visibility']
    TYPED_ATTR_NAMES = ["containing_structure"]
    def __init__(self, containing_structure: TypeParser.AbstractTAG) -> None:
      super().__init__()
      TypeParser.Accessible.__init__(self)
      TypeParser.Aligned.__init__(self)
      TypeParser.Declarable.__init__(self)
      TypeParser.Sized.__init__(self)
      TypeParser.Typed.__init__(self)
      self.containing_structure = containing_structure

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Accessible.parse(self, die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Declarable.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser)
      TypeParser.Typed.parse(self, die, parser)
      self.lower_bound = parser.get_die_attribute_block_or_int(die, 'DW_AT_lower_bound', default_value=0)
      self.upper_bound = parser.get_die_attribute_block_or_int_or_ref(die, 'DW_AT_upper_bound')
      count = parser.get_die_attribute_int(die, 'DW_AT_count')
      if self.upper_bound is None:
        self.upper_bound = count + self.lower_bound - 1 if count is not None else None
      self.byte_stride = parser.get_die_attribute_int(die, 'DW_AT_byte_stride', default_value=0)
      self.bit_stride = parser.get_die_attribute_int(die, 'DW_AT_bit_stride', default_value=0)

      if self.type is None and isinstance(self.containing_structure, TypeParser.Typed):
        self.type = self.containing_structure.type

    @property
    def count(self) -> int | None:
      if isinstance(self.lower_bound, int) and isinstance(self.upper_bound, int):
        return self.upper_bound - self.lower_bound + 1
      return None

    def byte_size(self) -> int:
      elem_size = None
      if TypeParser.Sized.byte_size(self) is not None:
        elem_size = TypeParser.Sized.byte_size(self)
      elif self.type is not None:
        elem_size = self.type.byte_size()

      if elem_size is not None:
        return elem_size * self.count
      else:
        raise Exception("Incomplete Subrange definition")

    def __eq__(self, __value: TypeParser.Subrange, compare_containing_structure: bool = True) -> bool:
      if not isinstance(__value, TypeParser.Subrange):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.Subrange.__bases__]) and \
             ((not compare_containing_structure) or self.containing_structure == __value.containing_structure) and \
             self.lower_bound == __value.lower_bound and \
             self.upper_bound == __value.upper_bound and \
             self.count == __value.count and \
             self.byte_stride == __value.byte_stride and \
             self.bit_stride == __value.bit_stride

    def __hash__(self) -> int:
      # Ignore containing structure for hash
      lower_bound_hash = self.lower_bound
      if isinstance(self.lower_bound, list):
        lower_bound_hash = hash(tuple(self.lower_bound))
      upper_bound_hash = self.upper_bound
      if isinstance(self.upper_bound, list):
        upper_bound_hash = hash(tuple(self.upper_bound))
      return hash((tuple([c.__hash__(self) for c in TypeParser.Subrange.__bases__]), \
                   lower_bound_hash, upper_bound_hash, self.count, self.byte_stride, self.bit_stride))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      # Subrange will always be extended
      return f"Subrange({self.type.__repr__(visited)}, {self.lower_bound}, {self.upper_bound})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      # Subrange will always be extended
      return f"[{self.count}]"

  class ArrayType(AbstractType, Accessible, Aligned, Declarable, Sized, Typed):
    DW_TAG = 'DW_TAG_array_type'
    IGNORED_ATTRIBUTES = ['DW_AT_start_scope', 'DW_AT_rank', 'DW_AT_data_location', 'DW_AT_associated',
                          'DW_AT_allocated']
    TYPED_ATTR_NAMES = ["specification", "dimensions"]

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Accessible.__init__(self)
      TypeParser.Aligned.__init__(self)
      TypeParser.Declarable.__init__(self)
      TypeParser.Sized.__init__(self)
      TypeParser.Typed.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Accessible.parse(self, die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Declarable.parse(self, die, parser)
      TypeParser.Sized.parse(self, die, parser)
      TypeParser.Typed.parse(self, die, parser, mandatory=True)
      self.type: TypeParser.AbstractType
      self.ordering = parser.get_die_attribute_int(die, 'DW_AT_ordering')
      self.byte_stride = parser.get_die_attribute_int(die, 'DW_AT_byte_stride')
      self.bit_stride = parser.get_die_attribute_int(die, 'DW_AT_bit_stride')
      self.specification = parser.get_die_attribute_ref(die, 'DW_AT_specification')
      self.visibility = parser.get_die_attribute_int(die, 'DW_AT_visibility')

      self.dimensions: list[TypeParser.Subrange] = [parser.parse_DIE(ch, containing_structure=self)
                                                    for ch in die.iter_children()
                                                    if ch.tag == TypeParser.Subrange.DW_TAG]

    def byte_size(self) -> int:
      # Check if Array size is stated explicitly
      if TypeParser.Sized.byte_size(self) is not None:
        return TypeParser.Sized.byte_size(self)

      # Otherwise, calculate size depending on stride
      total_elements = 1 if len(self.dimensions) > 0 else 0
      for dim in self.dimensions:
        total_elements *= dim.count

      if self.byte_stride:
        return self.byte_stride * total_elements
      elif self.bit_stride:
        return (self.bit_stride * total_elements + 7) // 8

      # Finally, calculate depending on type size
      return self.type.byte_size() * total_elements

    def get_dimensions(self):
      return self.dimensions

    def _compare_dimensions(self, __value: TypeParser.ArrayType) -> bool:
      if len(self.dimensions) != len(__value.dimensions):
        return False
      for self_dim, value_dim in zip(self.dimensions, __value.dimensions):
        if not self_dim.__eq__(value_dim, compare_containing_structure=False):
          return False
      return True

    def __eq__(self, __value: TypeParser.ArrayType) -> bool:
      if not isinstance(__value, TypeParser.ArrayType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.ArrayType.__bases__]) and \
             self._compare_dimensions(__value) and \
             self.ordering == __value.ordering and \
             self.byte_stride == __value.byte_stride and \
             self.bit_stride == __value.bit_stride and \
             self.accessibility == __value.accessibility and \
             self.specification == __value.specification and \
             self.visibility == __value.visibility

    def __hash__(self) -> int:
      # Specification is ignored for hash computation
      return hash((tuple([c.__hash__(self) for c in TypeParser.ArrayType.__bases__]), \
                   self.ordering, self.byte_stride, self.bit_stride, self.accessibility, self.visibility))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      # ArrayType will always be expanded
      dimensions_repr = ", ".join([dim.__repr__(visited) for dim in self.dimensions])
      return f"ArrayType({self.type.__repr__(visited)}, {dimensions_repr})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      # ArrayType will always be expanded
      dimensions_str = "".join([dim.__str__(visited) for dim in self.dimensions])
      return f"{self.type.__str__(visited) if self.type is not None else ''} {dimensions_str}"

  class FormalParameter(AbstractTAG, Artificial, Typed):
    DW_TAG = 'DW_TAG_formal_parameter'
    IGNORED_ATTRIBUTES = ['DW_AT_location', 'DW_AT_segment']
    TYPED_ATTR_NAMES = []
    def __init__(self) -> None:
      super().__init__()
      TypeParser.Artificial.__init__(self)
      TypeParser.Typed.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Artificial.parse(self, die, parser)
      TypeParser.Typed.parse(self, die, parser)
      self.const_value = parser.get_die_attribute_int(die, 'DW_AT_const_value') # Only 'const' supported, block or str not.
      self.default_value = parser.get_die_attribute_int(die, 'DW_AT_default_value') # Only 'const' supported, ref, block or str not.
      self.endianity = parser.get_die_attribute_int(die, 'DW_AT_endianity')
      self.is_optional = parser.get_die_attribute_flag(die, 'DW_AT_is_optional')
      self.variable_parameter = parser.get_die_attribute_flag(die, 'DW_AT_variable_parameter')

    def __eq__(self, __value: TypeParser.FormalParameter) -> bool:
      if not isinstance(__value, TypeParser.FormalParameter):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.FormalParameter.__bases__]) and \
             self.artificial == __value.artificial and \
             self.const_value == __value.const_value and \
             self.default_value == __value.default_value and \
             self.endianity == __value.endianity and \
             self.is_optional == __value.is_optional and \
             self.variable_parameter == __value.variable_parameter

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.FormalParameter.__bases__]), \
                   self.artificial, self.const_value, self.default_value, self.endianity, self.is_optional,
                   self.variable_parameter))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      # Formal Parameter will always be expanded
      type_repr = self.type.__repr__(visited) if self.type is not None else 'None'
      name_repr = self.name if self.name is not None else 'None'
      return f"FormalParameter({type_repr}, {name_repr})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      # Formal Parameter will always be expanded
      type_str = self.type.__str__(visited)
      if self.name is not None:
        type_str += ' ' + self.name
      return type_str

  class SubroutineType(AbstractType, Accessible, Aligned, Declarable, Typed):
    DW_TAG = 'DW_TAG_subroutine_type'
    IGNORED_ATTRIBUTES = ['DW_AT_address_class', 'DW_AT_allocated', 'DW_AT_associated', 'DW_AT_data_location',
                          'DW_AT_reference', 'DW_AT_rvalue_reference', 'DW_AT_start_scope', 'DW_AT_visibility']
    TYPED_ATTR_NAMES = ["parameters"]
    def __init__(self) -> None:
      super().__init__()
      TypeParser.Accessible.__init__(self)
      TypeParser.Aligned.__init__(self)
      TypeParser.Declarable.__init__(self)
      TypeParser.Typed.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Accessible.parse(self, die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Declarable.parse(self, die, parser)
      TypeParser.Typed.parse(self, die, parser)
      self.prototyped = parser.get_die_attribute_flag(die, 'DW_AT_prototyped')
      self.parameters = [parser.parse_DIE(ch)
                         for ch in die.iter_children()
                         if ch.tag == TypeParser.FormalParameter.DW_TAG]
      self.unspecified_parameters: bool = any([ch.tag == 'DW_TAG_unspecified_parameters' for ch in die.iter_children()])

    def byte_size(self) -> int:
      # Note: A subroutine itself does not have a size. When a reference to a subroutine is used (like in C or C++),
      # this is done hy having a PointerType to a SubroutineType, which specifies the byte size of the reference.
      return 0

    def _get_tag_dependencies(self, dependencies: list[TypeParser.AbstractTAG]) -> None:
      if not self in dependencies:
        dependencies.append(self)
        if self.type is not None:
          self.type._get_tag_dependencies(dependencies)
        for param in self.parameters:
          if param.type is not None:
            param.type._get_tag_dependencies(dependencies)

    def __eq__(self, __value: TypeParser.SubroutineType) -> bool:
      if not isinstance(__value, TypeParser.SubroutineType):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.SubroutineType.__bases__]) and \
             self.prototyped == __value.prototyped and \
             self.parameters == __value.parameters and \
             self.unspecified_parameters == __value.unspecified_parameters

    def __hash__(self) -> int:
      # Ignore parameters for hash computation
      return hash((tuple([c.__hash__(self) for c in TypeParser.SubroutineType.__bases__]), \
                   self.prototyped, self.unspecified_parameters))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"SubroutineType({self.name})"
      else:
        visited.append(self)
        return_type = self.type.__repr__(visited) if self.type is not None else 'void'
        parameters_repr = ", ".join([p.__repr__(visited) for p in self.parameters])
        return f"SubroutineType({self.name}, {return_type}, [{parameters_repr}], {self.unspecified_parameters})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"{self.name if self.name else ''}()"
      else:
        visited.append(self)
        return_type = self.type.__str__(visited) if self.type is not None else 'void'
        parameter_str = ", ".join([p.__str__(visited) for p in self.parameters])
        if self.unspecified_parameters:
          parameter_str += ", ..." if len(self.parameters) > 0 else "..."
        return f"{return_type} + {self.name if self.name else ''} ({parameter_str})"

  class Variable(AbstractTAG, Accessible, Aligned, Artificial, Declarable, Typed):
    DW_TAG = 'DW_TAG_variable'
    IGNORED_ATTRIBUTES = ['DW_AT_segment', 'DW_AT_start_scope']
    TYPED_ATTR_NAMES = ["specification"]

    def __init__(self) -> None:
      super().__init__()
      TypeParser.Accessible.__init__(self)
      TypeParser.Aligned.__init__(self)
      TypeParser.Artificial.__init__(self)
      TypeParser.Declarable.__init__(self)
      TypeParser.Typed.__init__(self)

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      TypeParser.Accessible.parse(self, die, parser)
      TypeParser.Aligned.parse(self, die, parser)
      TypeParser.Artificial.parse(self, die, parser)
      TypeParser.Declarable.parse(self, die, parser)
      TypeParser.Typed.parse(self, die, parser)
      self.external = parser.get_die_attribute_flag(die, 'DW_AT_external')
      self.const_expr = parser.get_die_attribute_flag(die, 'DW_AT_const_expr')
      self.const_value = parser.get_die_attribute_block_or_int(die, 'DW_AT_const_value')

      self.endianity = parser.get_die_attribute_int(die, 'DW_AT_endianity')
      self.linkage_name = parser.get_die_attribute_str(die, 'DW_AT_linkage_name')
      if self.linkage_name is None:
        # Support gcc/g++ extension
        self.linkage_name = parser.get_die_attribute_str(die, 'DW_AT_MIPS_linkage_name')
      self.visibility = parser.get_die_attribute_int(die, 'DW_AT_visibility')
      self.specification = parser.get_die_attribute_ref(die, 'DW_AT_specification')
      assert(self.specification is None or isinstance(self.specification, self.__class__))
      location_bytes = parser.get_die_attribute_block_or_int(die, 'DW_AT_location')
      if (isinstance(location_bytes, list)):
        self.location = int.from_bytes(location_bytes[1:], byteorder='little', signed=False)
      else:
        self.location = location_bytes
      # Inline for C++17 support
      self.inline = parser.get_die_attribute_int(die, 'DW_AT_inline')
      # GNU:
      self.GNU_locviews = parser.get_die_attribute_int(die, 'DW_AT_GNU_locviews')

      # If the variable is an external declaration, search for the specification
      if self.declaration and self.external:
        sibling: DIE
        for sibling in die.iter_siblings():
          if sibling.tag == self.DW_TAG and parser.get_die_attribute_ref_DIE(sibling, 'DW_AT_specification') == self.die:
            # Parse the sibling
            specification = parser.parse_DIE(sibling)
            assert(isinstance(specification, self.__class__))
            specification.update_from(self)
            break

    def get_name(self) -> str|None:
      if self.name is not None:
        return self.name
      elif self.specification:
        return self.specification.get_name()
      else:
        return super().get_name()

    def get_location(self) -> int|None:
      return self.location

    def is_const_value(self) -> bool:
      if self.const_expr is not None:
        return self.const_expr
      if self.specification is not None and self.specification.const_expr is not None:
        return self.specification.const_expr
      return False

    def get_const_value(self) -> Any:
      if self.const_value is not None:
        return self.const_value
      if self.specification is not None and self.specification.const_value is not None:
        return self.specification.const_value
      return None

    def get_type(self) -> TypeParser.AbstractTAG|None:
      # Check self
      if self.type is not None:
        return self.type
      # Check specification
      if self.specification is not None and self.specification.type is not None:
        return self.specification.type
      return self.type

    def __eq__(self, __value: TypeParser.Variable) -> bool:
      if not isinstance(__value, self.__class__):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in self.__class__.__bases__]) and \
             self.external == __value.external and \
             self.accessibility == __value.accessibility and \
             self.artificial == __value.artificial and \
             self.const_value == __value.const_value and \
             self.endianity == __value.endianity and \
             self.linkage_name == __value.linkage_name and \
             self.visibility == __value.visibility and \
             self.specification == __value.specification and \
             self.location == __value.location

    def __hash__(self) -> int:
      # Ignore specification for hash computation
      return hash((tuple([c.__hash__(self) for c in TypeParser.Variable.__bases__]), \
                   self.external, self.accessibility, self.artificial, self.endianity,
                   self.linkage_name, self.visibility, self.location,
                   self.const_value if not isinstance(self.const_value, list) else tuple(self.const_value)))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      type = self.type.__repr__(visited) if self.type is not None else 'void'
      return f"Variable({self.name}, {type}, {self.location})"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      type = self.type.__str__(visited) if self.type is not None else 'void'
      location = hex(self.location) if self.location is not None else 'unknown location'
      return f"{type} {self.get_name()} @ {location}"

  class Namespace(AbstractTAG):
    DW_TAG = 'DW_TAG_namespace'
    IGNORED_ATTRIBUTES = []
    TYPED_ATTR_NAMES = ["namespace_members"]
    def __init__(self) -> None:
      super().__init__()
      self.namespace_members: list[TypeParser.AbstractTAG] = []

    def parse(self, die: DIE, parser: TypeParser):
      super().parse(die, parser)
      self.export_symbols = parser.get_die_attribute_flag(die, 'DW_AT_export_symbols')
    
      # if symbols are exported, all members need to be parsed. Otherwise, only parse on request
      if self.export_symbols:
        self.parse_members(parser)
     
    def parse_members(self, parser: TypeParser):
      # Parse all members
      self.namespace_members = [parser.parse_DIE(ch)
                                for ch in self.die.iter_children()
                                if parser.is_DIE_parsable(ch)]
      
      # Set self as namespace in all members
      for m in self.namespace_members:
        m.set_namespace(self)

    def parse_members_named(self, parser: TypeParser, names: list[str], namespace_separator: str):
      namespace_bases = [t.split(namespace_separator)[0] for t in names]
      self.namespace_members = [parser.parse_DIE(ch)
                                for ch in self.die.iter_children()
                                if parser.is_DIE_parsable(ch) and 
                                   parser.get_die_attribute_str(ch, 'DW_AT_name') in namespace_bases]
      
      for m in self.namespace_members:
        m.set_namespace(self)
        # Recursively parse all named namespaces
        if isinstance(m, TypeParser.Namespace) and not m.export_symbols:
          namespace_type_names = [t.split(namespace_separator, 1)[1] 
                                  for t in names 
                                  if t.split(namespace_separator, 1)[0] == m.name]
          m.parse_members_named(parser, namespace_type_names, namespace_separator)

    def byte_size(self) -> int:
      return 0      

    def __eq__(self, __value: TypeParser.Namespace) -> bool:
      if not isinstance(__value, TypeParser.Namespace):
        return NotImplemented
      return all([c.__eq__(self, __value) for c in TypeParser.Namespace.__bases__]) and \
             self.export_symbols == __value.export_symbols

    def __hash__(self) -> int:
      return hash((tuple([c.__hash__(self) for c in TypeParser.Namespace.__bases__]), \
                   self.export_symbols))

    def __repr__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"Namespace({self.name})"
      else:
        visited.append(self)
        namespace_member_repr = ", ".join([m.__repr__(visited) for m in self.namespace_members])
        return f"Namespace({self.name}, {self.export_symbols}, [{namespace_member_repr}], )"

    def __str__(self, visited: list[TypeParser.AbstractTAG]|None = None) -> str:
      visited = visited or []
      if self in visited:
        return f"Namespace {self.name if self.name else ''}"
      else:
        visited.append(self)
        namespace_member_str = "\n".join(['\t' + m.__str__(visited) for m in self.namespace_members])
        return f"Namespace {self.name if self.name else ''}:\n{namespace_member_str}\n"

  def __init__(self,
               elf_file: str|BytesIO,
               allow_duplicates: bool = False,
               catch_exceptions: bool = False,
               type_names: None|list[str] = None):
    # Initialize private variables
    self._parsable_classes = [c for c in self._get_subclasses_of_class(TypeParser.AbstractTAG) if isinstance(c.DW_TAG, str)]
    self._parsable_TAG_to_class_dict: dict[str, type[TypeParser.AbstractTAG]] = dict([(c.DW_TAG, c) for c in self._parsable_classes])
    self._allow_duplicates = allow_duplicates
    self.catch_exceptions = catch_exceptions

    # Helper lists and dicts for parsing TAGs
    self._unparsable_TAGs: list[str] = []
    self._unparsed_TAGs: list[TypeParser.AbstractTAG] = []
    self._unsorted_TAGs: list[TypeParser.AbstractTAG] = []
    self._parsed_die_attributes: dict[int, list[str]] = {}
    self._unsupported_TAG_class_attributes: dict[type[TypeParser.AbstractTAG], list[str]] = {}

    # Initialize dictionaries for parsed TAG tracking
    self._TAG_CU_offset_dict: dict[CompileUnit, dict[int, TypeParser.AbstractTAG]] = {}
    self._TAG_class_hash_dict: dict[type[TypeParser.AbstractTAG], dict[int, list[TypeParser.AbstractTAG]]] = {}

    # Variables for tracking not completely linked TAGs
    self.unlinked: list[TypeParser.Variable] = []

    # Initialize other default values
    self._namespace_string_separator: str = "::"

    # Open and extract ELF file
    if isinstance(elf_file, str):
      elf_file_bytes = open(elf_file, 'rb')
    else:
      elf_file_bytes = elf_file

    self.elffile = ELFFile(elf_file_bytes)

    # Check if ELF file has a DWARF info section
    if not self.elffile.has_dwarf_info():
      raise Exception('file has no DWARF info')
    self.dwarfinfo = self.elffile.get_dwarf_info()
    if not self.dwarfinfo.has_debug_info:
      raise Exception('file has no debug info')

    # Extract the Symbol Table
    symtab = self.elffile.get_section_by_name(".symtab")
    if not isinstance(symtab, SymbolTableSection):
      raise Exception('Unable to extract symbol table')
    self.symtab = symtab

    # Extract Types and global variables
    print(f"[TypeParser] Info: Extracting TAGS from {elf_file}.")
    self._extract(type_names)

    if isinstance(elf_file, str):
      elf_file_bytes.close()

  def get_die_attribute(self,
                        die: DIE,
                        attribute_name: str,
                        expected_form: str | Iterable[str],
                        /, *,
                        default_value: Any = None,
                        mandatory: bool = False
                        ) -> Any|None:
      # Mark the attribute as parsed, independent of success
      self._parsed_die_attribute(die, attribute_name)

      # Check if the attribute exists
      if not attribute_name in die.attributes:
        if mandatory:
          raise Exception(f"DIE does not have mandatory Attribute {attribute_name}:\n{die}")
        else:
          return default_value
      attribute = die.attributes.get(attribute_name)

      # Get and check the value
      value = getattr(attribute, "value", None)
      if value is None:
        if mandatory:
          raise Exception(f"DIE does not have a value for mandatory Attribute {attribute_name}:\n{die}")
        else:
          return default_value

      # Get and check the form
      if isinstance(expected_form, str):
        expected_form = [expected_form]
      form = getattr(attribute, "form", None)
      if form is None or not form in expected_form:
        raise Exception(f"DIE Attribute {attribute_name} has form {form}, but expected any of {expected_form}:\n{attribute}")
      # return the parsed value
      return value

  def get_die_attribute_block(self,
                              die: DIE,
                              attribute_name: str,
                              /, *,
                              default_value: list|None = None,
                              mandatory: bool = False
                              ) -> list[int]|None:
    # Get the attribute and check attribute form
    expected_form = ["DW_FORM_block", "DW_FORM_block1", "DW_FORM_block2", "DW_FORM_block4", "DW_FORM_exprloc"]
    value = self.get_die_attribute(die, attribute_name, expected_form, mandatory=mandatory)

    # Return default value if attribute is not present
    if value is None:
      return default_value
    return value

  def get_die_attribute_block_or_int(self,
                                     die: DIE,
                                     attribute_name: str,
                                     /, *,
                                     default_value: list|int|None = None,
                                     mandatory: bool = False
                                     ) -> list[int]|int|None:
    expected_form = ["DW_FORM_block", "DW_FORM_block1", "DW_FORM_block2", "DW_FORM_block4", "DW_FORM_exprloc",
                     "DW_FORM_data1", "DW_FORM_data2", "DW_FORM_data4", "DW_FORM_data8", "DW_FORM_data16",
                     "DW_FORM_sdata", "DW_FORM_udata", 'DW_FORM_implicit_const', "DW_FORM_sec_offset"]
    value = self.get_die_attribute(die, attribute_name, expected_form, mandatory=mandatory)
    if value is None:
      return default_value
    if isinstance(value, list):
      return value
    return int(value)

  def get_die_attribute_flag(self,
                             die: DIE,
                             attribute_name: str,
                             /, *,
                             default_value: bool|None = None,
                             mandatory: bool = False
                             ) -> bool|None:
    expected_form = ["DW_FORM_flag", "DW_FORM_flag_present"]
    value = self.get_die_attribute(die, attribute_name, expected_form, mandatory=mandatory)
    return bool(value) if value is not None else default_value

  def get_die_attribute_int(self,
                            die: DIE,
                            attribute_name: str,
                            /, *,
                            default_value: int|None = None,
                            mandatory: bool = False
                            ) -> int|None:
    expected_form = ["DW_FORM_data1", "DW_FORM_data2", "DW_FORM_data4", "DW_FORM_data8", "DW_FORM_data16",
                     "DW_FORM_sdata", "DW_FORM_udata", "DW_FORM_implicit_const", "DW_FORM_sec_offset"]
    value = self.get_die_attribute(die, attribute_name, expected_form, mandatory=mandatory)
    int_value = default_value
    try:
      int_value = int(value)
    finally:
      return int_value

  def get_die_attribute_ref(self,
                            die: DIE,
                            attribute_name: str,
                            /, *,
                            default_value: TypeParser.AbstractTAG|None = None,
                            mandatory: bool = False,
                            ) -> TypeParser.AbstractTAG|None:
    type_die = self.get_die_attribute_ref_DIE(die, attribute_name, default_value=default_value, mandatory=mandatory)
    if type_die is not None:
      if self.catch_exceptions:
        try:
          return self.parse_DIE(type_die)
        except Exception as e:
          raise Exception(f"Failed to parse reference of attribute {attribute_name} of DIE \n{die}\nCause: {e}")
      else:
        return self.parse_DIE(type_die)
    else:
      return default_value
    
  def get_die_attribute_ref_DIE(self,
                                die: DIE,
                                attribute_name: str,
                                /, *,
                                default_value: DIE|None = None,
                                mandatory: bool = False,
                                ) -> DIE|None:
    expected_form = ["DW_FORM_ref1", "DW_FORM_ref2", "DW_FORM_ref4", "DW_FORM_ref8", "DW_FORM_ref_udata",
                     "DW_FORM_ref_addr", "DW_FORM_ref_sup4", "DW_FORM_ref_sig8"]
    value = self.get_die_attribute(die, attribute_name, expected_form, mandatory=mandatory)
    cu: CompileUnit = die.cu
    if value is not None:
      return cu.get_DIE_from_refaddr(value + cu.cu_offset)
    else:
      return default_value
    
  def get_die_attribute_block_or_int_or_ref(self,
                                            die: DIE,
                                            attribute_name: str,
                                            /, *,
                                            default_value: list|int|None = None,
                                            mandatory: bool = False
                                            ) -> list[int]|int|None:
    attribute = die.attributes.get(attribute_name)
    form = getattr(attribute, "form", None)
    if form is not None and form in ["DW_FORM_ref1", "DW_FORM_ref2", "DW_FORM_ref4", 
                                      "DW_FORM_ref8", "DW_FORM_ref_udata",
                                      "DW_FORM_ref_addr", "DW_FORM_ref_sup4", "DW_FORM_ref_sig8"]:
      return self.get_die_attribute_ref(die, attribute_name, default_value=default_value, mandatory=mandatory)
    else:
      return self.get_die_attribute_block_or_int(die, attribute_name, default_value=default_value, mandatory=mandatory)

  def get_die_attribute_ref_unparsed(self,
                                     die: DIE,
                                     attribute_name: str,
                                     /, *,
                                     default_value: DIE|None = None,
                                     mandatory: bool = False,
                                     ) -> DIE|None:
    expected_form = ["DW_FORM_ref1", "DW_FORM_ref2", "DW_FORM_ref4", "DW_FORM_ref8", "DW_FORM_ref_udata",
                     "DW_FORM_ref_addr", "DW_FORM_ref_sup4", "DW_FORM_ref_sig8"]
    value = self.get_die_attribute(die, attribute_name, expected_form, mandatory=mandatory)
    cu: CompileUnit = die.cu
    if value is not None:
      return cu.get_DIE_from_refaddr(value + cu.cu_offset)
    else:
      return default_value

  def get_die_attribute_str(self,
                            die: DIE,
                            attribute_name: str,
                            /, *,
                            default_value: str|None = None,
                            mandatory: bool = False
                            ) -> str|None:
    expected_form = ["DW_FORM_string", "DW_FORM_strp", "DW_FORM_line_strp", "DW_FORM_strp_sup",
                     "DW_FORM_strx", "DW_FORM_strx1", "DW_FORM_strx2", "DW_FORM_strx3", "DW_FORM_strx4",
                     "DW_FORM_implicit_const"]
    value = self.get_die_attribute(die, attribute_name, expected_form, mandatory=mandatory)
    return value.decode() if value is not None else default_value

  def get_tags(self) -> list[AbstractTAG]:
    tag_list = []
    for hash_tag_dict in self._TAG_class_hash_dict.values():
      for hash_tag_list in hash_tag_dict.values():
        tag_list.extend(hash_tag_list)
    return tag_list

  def get_tags_by_name(self, type_name: str) -> list[AbstractTAG]:
    name_elements = type_name.split(self._namespace_string_separator)
    if len(name_elements) > 1:
      namespace_name = name_elements.pop(0)
      namespaces: list[TypeParser.Namespace] = [n for n in self.get_tags_by_class(TypeParser.Namespace) 
                                                if n.name == namespace_name]
      while len(name_elements) > 1:
        namespace_name = name_elements.pop(0)
        namespaces = [m for n in namespaces 
                        for m in n.namespace_members 
                        if isinstance(m, TypeParser.Namespace) and m.name == namespace_name]

      tag_list = [m for n in namespaces 
                  for m in n.namespace_members]
    else:
      tag_list = self.get_tags()
    
    return [type for type in tag_list if isinstance(type, TypeParser.Named) and type.name == name_elements[0]]

  def get_tags_by_class(self, type_class: type[AbstractTAG]) -> list[AbstractType]:
    tag_list = []
    for cls, class_hash_tag_lists in self._TAG_class_hash_dict.items():
      if issubclass(cls, type_class):
        for hash_tag_list in class_hash_tag_lists.values():
          tag_list.extend(hash_tag_list)
    return tag_list

  def get_types(self) -> list[AbstractType]:
    tag_list = []
    for cls, hash_tag_dict in self._TAG_class_hash_dict.items():
      if issubclass(cls, TypeParser.AbstractType):
        for hash_tag_list in hash_tag_dict.values():
          tag_list.extend(hash_tag_list)
    return tag_list

  def get_global_variables(self) -> list[Variable]:
    tag_list = []
    if TypeParser.Variable in self._TAG_class_hash_dict:
      for hash_tag_list in self._TAG_class_hash_dict[TypeParser.Variable].values():
        tag_list.extend(hash_tag_list)
    return tag_list
  
  def set_namespace_string_separator(self, separator: str) -> None:
    self._namespace_string_separator = separator

  def get_namespace_string_separator(self) -> str:
    return self._namespace_string_separator
  
  def _extract(self, type_names: list[str]|None = None) -> None:
    if type_names is None:
      print(f"[TypeParser] Info: Beginning TAG extraction.")
    else:
      print(f"[TypeParser] Info: Beginning TAG extraction of: {type_names}")

    for cu in self.dwarfinfo.iter_CUs():
      if not isinstance(cu, CompileUnit):
        raise Exception(f"Not a compile Unit: {cu}")
      top_die = cu.get_top_DIE() 
      if top_die is not None:
        if not isinstance(top_die, DIE):
          raise Exception(f"Not a DIE: {top_die}")
        for die in top_die.iter_children():
          if not isinstance(die, DIE):
            raise Exception(f"Not a DIE: {top_die}")
          self._extract_die_named(die, type_names)
          
    self._post_parse()

  def _extract_die_named(self, die: DIE, type_names: list[str]|None) -> AbstractTAG|None:
    if type_names is None:
      return self._extract_die(die)
    
    if self._namespace_string_separator:
      type_name_bases = [t.split(self._namespace_string_separator)[0] for t in type_names]  
    
    name = self.get_die_attribute_str(die, 'DW_AT_name')
    if name is not None and name in type_name_bases:
      die = self._extract_die(die)
      if isinstance(die, TypeParser.Namespace) and not die.export_symbols:
        namespace_type_names = [t.split(self._namespace_string_separator, 1)[1] 
                                for t in type_names 
                                if t.split(self._namespace_string_separator, 1)[0] == die.name]
        die.parse_members_named(self, namespace_type_names, self._namespace_string_separator)
      return die

  def _extract_die(self, die: DIE) -> AbstractTAG|None:
    if self.is_DIE_parsable(die):
      tag: TypeParser.AbstractTAG
      if self.catch_exceptions:
        try:
          tag = self.parse_DIE(die)
        except Exception as e:
          print(f"[TypeParser] Warning: Failed to parse DIE: {die} {e}")
          return
      else:
        tag = self.parse_DIE(die)
      return tag
    else:
      self._report_unparsable_tag(die)
      return None

  def _report_unparsable_tag(self, die: DIE):
    die_tag = str(die.tag)
    if die_tag not in self._unparsable_TAGs:
      self._unparsable_TAGs.append(die_tag)
      print(f"[TypeParser] Warning: Encountered unparsable TAG: {die.tag}.")

  def _post_parse(self) -> None:
    # Count the number of types extracted
    print(f"[TypeParser] Info: {len(self.get_tags())} TAGs extracted.")
    print(f"[TypeParser] Info: Starting secondary linking phase.")

    # Complete Declarations
    self.completed_declarations, self.uncompleted_declarations = self._complete_declaration()
    if len(self.completed_declarations) > 0:
      print(f"[TypeParser] Info: completed {len(self.completed_declarations)} type declaration(s).")
    if len(self.uncompleted_declarations) > 0:
      uncompleted_names_str = "\n".join([" - " + u.name for u in self.uncompleted_declarations if u.name is not None])
      print(f"[TypeParser] Warning: {len(self.uncompleted_declarations)} type declaration(s) remain incomplete:\n{uncompleted_names_str}")

    # Check for remaining duplicate types
    print(f"[TypeParser] Info: Checking for duplicates.")
    self.duplicates = self._get_duplicates()
    print(f"[TypeParser] Info: Found {len(self.duplicates)} duplicate parsed TAGs in total.")
    duplicate_updated_tags = self._remove_duplicates()
    if len(duplicate_updated_tags) > 0:
      print(f"[TypeParser] Info: Updated {len(duplicate_updated_tags)} TAGs that were referencing duplicates.")

    # Validate the internal type references
    print(f"[TypeParser] Info: Checking for invalid references.")
    self.invalid_references = self._validate_references()
    if len(self.invalid_references) > 0:
      print(f"[TypeParser] Warning: Found {len(self.invalid_references)} TAGs with an invalid reference.")

    print(f"[TypeParser] Info: Finished Type Extraction.")
    print(f"[TypeParser] Info: {len(self.get_tags())} TAGs extracted:")
    for cls, hash_dict in self._TAG_class_hash_dict.items():
      num_tags_per_class = sum([len(tag_list) for tag_list in hash_dict.values()])
      print(f"{str(num_tags_per_class).rjust(6)} {cls.__name__}")

  def _complete_declaration(self) -> tuple[list[TypeParser.Declarable], list[TypeParser.Declarable]]:
    uncompleted: list[TypeParser.Declarable] = []
    completed: list[TypeParser.Declarable] = []
    # Filter all Types that are a declaration
    declaration_types = [t for t in self.get_tags() if isinstance(t, TypeParser.Declarable) and t.declaration]
    for declaration_type in declaration_types:
      # Cannot complete unnamed types, as name is used to find the completing type
      if declaration_type.name is None:
        uncompleted.append(declaration_type)
      else:
        # Find types that (1) have the same class, (2) are not declarations themselves, (3) are named and
        # (4) have the same name as the declaration as completion candidates
        completion_types = [t
                            for hash_list in self._TAG_class_hash_dict[declaration_type.__class__].values()
                            for t in hash_list
                            if not t.declaration
                              and t.name is not None
                              and t.name == declaration_type.name]
        if len(completion_types) >= 1:
          # Update all completions with the information from the declaration
          for completion in completion_types:
            completion.update_from(declaration_type)
            self.resort_TAG(completion)
          self._remove_TAG_exact(declaration_type, deinit=True, replacement=completion_types[0])
          completed.append(declaration_type)
        else:
          uncompleted.append(declaration_type)
    return completed, uncompleted

  def _get_duplicates(self) -> dict[TypeParser.AbstractTAG, list[TypeParser.AbstractTAG]]:
    # Dict containing the duplicates, the 'original' is used as a key
    duplicates: dict[TypeParser.AbstractTAG, list[TypeParser.AbstractTAG]] = {}
    # Find all duplicates. Use _TAG_class_dict for speed optimization (only check within same class)
    for cls, tag_by_hash_dict in self._TAG_class_hash_dict.items():
      n_tot: int = 0
      class_duplicates: dict[TypeParser.AbstractTAG, list[TypeParser.AbstractTAG]] = {}
      # Go through the list hash by hash
      for tag_by_hash_list in tag_by_hash_dict.values():
        hash_uniques: list[TypeParser.AbstractTAG] = []
        n_tot += len(tag_by_hash_list)
        for tag in tag_by_hash_list:
          if not tag in hash_uniques:
            hash_uniques.append(tag)
          else:
            original = hash_uniques[hash_uniques.index(tag)]
            if original in class_duplicates:
              class_duplicates[original].append(tag)
            else:
              class_duplicates[original] = [tag]
      # Print statistics per class
      n_dup = sum([len(dup_list) for dup_list in class_duplicates.values()])
      n_uniq = n_tot - n_dup
      if n_dup != 0:
        print(f"[TypeParser] Info: Found {n_dup} duplicates in {n_tot} TAGs ({n_uniq} unique) of class {cls.__name__}")
      duplicates.update(class_duplicates)
    # return all found duplicates
    return duplicates

  def _remove_duplicates(self,
                         duplicates: dict[TypeParser.AbstractTAG, list[TypeParser.AbstractTAG]]|None = None
                         ) -> set[TypeParser.AbstractTAG]:
    """ Note: This function is very slow and inefficient"""
    if duplicates is None:
      duplicates = self.duplicates

    # Iterate over all parsed TAGs
    updated: set[TypeParser.AbstractTAG] = set()
    for class_, hash_TAG_dicts in self._TAG_class_hash_dict.items():
      tag_list = sum(hash_TAG_dicts.values(), [])
      base_classes = self._get_baseclasses_of_class(class_)
      typed_attr_names = sum([base.TYPED_ATTR_NAMES for base in base_classes], []) # type: ignore
      for tag in tag_list:
        # Iterate over all typed attributes of the TAG
        for attr_name in typed_attr_names:
          attr_value = getattr(tag, attr_name)
          # Determine type of attribute value
          attr_value_tag = None
          attr_value_list = None
          if attr_value is None:
            continue
          elif isinstance(attr_value, TypeParser.AbstractTAG):
            attr_value_tag = attr_value
          elif isinstance(attr_value, list):
            attr_value_list = attr_value
          else:
            raise Exception(f"""[TypeParser] Error: Cannot update reference to duplicate object. TAG '{tag.get_name()}'
                                of class '{class_.__name__}' has attribute '{attr_name}' of type
                                '{attr_value.__class__.__name__}' with unknown duplicate replacement sequence.""")
          # Iterate over all duplicates
          for original, duplicate_list in duplicates.items():
            for duplicate in duplicate_list:
              if attr_value_tag is not None:
                if attr_value_tag is duplicate:
                  setattr(tag, attr_name, original)
                  updated.add(tag)
              if attr_value_list is not None:
                for idx, item in enumerate(attr_value_list):
                  if item is duplicate:
                    attr_value_list[idx] = original
                    updated.add(tag)

    # Remove from TAG from parser lists
    for duplicate_list in duplicates.values():
      for duplicate in duplicate_list:
        self._remove_TAG_exact(duplicate, deinit=True, replacement=original)

    # Repeat
    self.duplicates = self._get_duplicates()
    if len(self.duplicates) > 0:
      updated.update(self._remove_duplicates())

    return updated

  def _validate_references(self) -> list[tuple[TypeParser.AbstractTAG, str, int|None]]:
    """ Note: This function is very slow and inefficient"""

    # Iterate over all parsed TAGs
    invalid_references: list[tuple[TypeParser.AbstractTAG, str, int|None]] = []
    for class_, hash_TAG_dicts in self._TAG_class_hash_dict.items():
      tag_list = sum(hash_TAG_dicts.values(), [])
      base_classes = self._get_baseclasses_of_class(class_)
      typed_attr_names = sum([base.TYPED_ATTR_NAMES for base in base_classes], []) # type: ignore
      for tag in tag_list:
        # Iterate over all typed attributes of the TAG
        for attr_name in typed_attr_names:
          attr_value = getattr(tag, attr_name)
          if attr_value is None:
            continue
          elif isinstance(attr_value, TypeParser.AbstractTAG):
            if not self._is_tag_in_tag_list(attr_value):
              invalid_references.append((tag, attr_name, None))
          elif isinstance(attr_value, list):
            for idx, item in enumerate(attr_value):
              if not self._is_tag_in_tag_list(item):
                invalid_references.append((tag, attr_name, idx))
          else:
            raise Exception(f"""[TypeParser] Error: Cannot validate reference. TAG '{tag.get_name()}'
                                of class '{class_.__name__}' has attribute '{attr_name}' of type
                                '{attr_value.__class__.__name__}' has an unknown reference detection type.""")
    return invalid_references

  def _is_tag_in_tag_list(self, tag: TypeParser.AbstractTAG) -> bool:
    tag_cls = tag.__class__
    tag_hash = hash(tag)
    if tag_cls in self._TAG_class_hash_dict and tag_hash in self._TAG_class_hash_dict[tag_cls]:
      for candidate in self._TAG_class_hash_dict[tag_cls][tag_hash]:
        if candidate is tag:
          return True
    return False

  @classmethod
  def _get_subclasses_of_class(cls, of_class: type) -> list[type]:
    subclasses = of_class.__subclasses__()
    all_subclasses = list(subclasses)
    for sc in subclasses:
      all_subclasses.extend(cls._get_subclasses_of_class(sc))
    return all_subclasses

  @classmethod
  def _get_baseclasses_of_class(cls, of_class: type) -> list[type]:
    bases = of_class.__bases__
    all_bases = list(bases)
    for base in bases:
      bases_of_base = cls._get_baseclasses_of_class(base)
      bases_of_base = [b for b in bases_of_base if not b in (ABC, object)]
      all_bases.extend(bases_of_base)
    return all_bases

  def is_DIE_parsable(self, die: DIE) -> bool:
    return (die is not None) and (die.tag in self._parsable_TAG_to_class_dict)

  def add_TAG(self, tag: TypeParser.AbstractTAG):
    # Add to _TAG_CU_offset_dict to allow offset tracking when resolving references
    self._TAG_CU_offset_dict[tag.die.cu][tag.die.offset] = tag

    # Add to _TAG_class_hash_dict to track TAGs first by classes and second by hash
    tag_hash = hash(tag)
    if not tag.__class__ in self._TAG_class_hash_dict:
      self._TAG_class_hash_dict[tag.__class__] = {tag_hash: [tag]}
    else:
      TAG_hash_dict = self._TAG_class_hash_dict[tag.__class__]
      if tag_hash in TAG_hash_dict:
        TAG_hash_dict[tag_hash].append(tag)
      else:
        TAG_hash_dict[tag_hash] = [tag]

  def remove_TAG(self, tag: TypeParser.AbstractTAG):
    # Remove from _TAG_CU_offset_dict
    self._TAG_CU_offset_dict[tag.die.cu].pop(tag.die.offset)

    # Remove from _TAG_class_dict
    self._TAG_class_hash_dict[tag.__class__][hash(tag)].remove(tag)

  def _remove_TAG_exact(self, 
                        tag_to_remove: TypeParser.AbstractTAG, *, 
                        deinit: bool = True,
                        replacement: TypeParser.AbstractTAG|None = None):
    # update self._TAG_CU_offset_dict
    for tag_dict in self._TAG_CU_offset_dict.values():
      remove_offsets = []
      for offset, tag in tag_dict.items():
        if tag is tag_to_remove:
          remove_offsets.append(offset)
      for offset in remove_offsets:
        tag_dict.pop(offset)

    # update self._TAG_class_hash_dict
    tag_dict = self._TAG_class_hash_dict[tag_to_remove.__class__]
    for tag_list in tag_dict.values():
      remove_idx = []
      for idx, tag in enumerate(tag_list):
        if tag is tag_to_remove:
          remove_idx.append(idx)
      remove_idx.reverse()
      for idx in remove_idx:
        tag_list.pop(idx)

    # De-init the tag to remove
    if deinit:
      tag_to_remove.deinit(replacement)

  def resort_TAG(self, tag: TypeParser.AbstractTAG):
    # Remove the tag from the current dicts exactly
    self._remove_TAG_exact(tag, deinit=False, replacement=None)
    # Add it again and sort it correctly
    self.add_TAG(tag)

  def parse_DIE(self, die: DIE, **kwargs) -> TypeParser.AbstractTAG:
    # Check if the die was already parsed and added to the _TAG_CU_offset_dict
    if not die.cu in self._TAG_CU_offset_dict:
      self._TAG_CU_offset_dict[die.cu] = {}
    TAG_offset_dict = self._TAG_CU_offset_dict[die.cu]
    if die.offset in TAG_offset_dict:
      return TAG_offset_dict[die.offset]

    # Initialize TAG using the corresponding subclass
    if die.tag in self._parsable_TAG_to_class_dict:
      tag = self._parsable_TAG_to_class_dict[die.tag](**kwargs)
    else:
      raise Exception(f"Cannot parse DIE:\n" + str(die) + "\n Supported TAGs: " + str(list(self._parsable_TAG_to_class_dict.keys())))

    # Add to _TAG_CU_offset_dict to allow offset tracking when resolving references and prevent circular dependencies
    self._TAG_CU_offset_dict[die.cu][die.offset] = tag

    # Keep track of TAGs being parsed
    self._unparsed_TAGs.append(tag)

    # Parse TAG
    tag.parse(die, self)
    tag.parse_complete()

    # Check unparsed attributes
    parsed_attribute_name_set = set(self._parsed_die_attributes.pop(id(die), []))
    attribute_name_set = set(die.attributes.keys())
    unparsed_attributes = attribute_name_set.difference(parsed_attribute_name_set)
    if len(unparsed_attributes) > 0:
      name = f"'{tag.name}'" if tag.name is not None else "unnamed TAG"
      cls = tag.__class__.__name__
      print(f"[TypeParser] Warning: While parsing {name} of class {cls}, ignored attribute(s): {unparsed_attributes}")

    # After parsing the TAG, remove it form the unparsed list (using 'is' and not '==' for exact matching)
    for (idx, unparsed) in enumerate(self._unparsed_TAGs):
      if unparsed is tag:
        self._unparsed_TAGs.pop(idx)
        break

    # If unparsed TAGs remain, it may not be possible to sort the the parsed TAG, as it may reference
    # an unparsed TAG. Add it to a list of unsorted TAGs that will be sorted once no unparsed TAGs remain
    self._unsorted_TAGs.append(tag)

    # Sort all parsed, but unsorted TAGs if no unsorted TAGs remain
    if len(self._unparsed_TAGs) == 0:
      self._sort_unsorted_TAGs()

    # Return the TAG
    return tag

  def _sort_unsorted_TAGs(self) -> None:
    for unsorted_TAG in self._unsorted_TAGs:
      # Hash the parsed tag
      tag_hash = hash(unsorted_TAG)
      cls = unsorted_TAG.__class__
      sort_as_TAG = unsorted_TAG

      # If duplicates are not allowed, check if the parsed DIE is a duplicate of an already parsed DIE
      is_duplicate = False
      if not self._allow_duplicates:
        if cls in self._TAG_class_hash_dict and tag_hash in self._TAG_class_hash_dict[cls]:
          # Check all parsed TAGs of the same class with the same hash if they are equal
          original_candidates = self._TAG_class_hash_dict[cls][tag_hash]
          for candidate in original_candidates:
            if unsorted_TAG == candidate:
              # If an equal TAG is found, use the 'original' instead of the duplicate
              sort_as_TAG = candidate
              is_duplicate = True
              break

      if is_duplicate:
        # Overwrite the reference in the _TAG_CU_offset_dict to the original
        self._TAG_CU_offset_dict[unsorted_TAG.die.cu][unsorted_TAG.die.offset] = sort_as_TAG
        # De-init the unsorted tag
        unsorted_TAG.deinit(replacement = sort_as_TAG)
      else:
        # Add to _TAG_class_hash_dict to sort them by class and hash (for quick duplicate checking)
        # If it's a duplicate, the original is already in the dict and does not have to be added.
        self.add_TAG(unsorted_TAG)

    # Clear the unsorted TAG list after sorting
    self._unsorted_TAGs.clear()

  def _parsed_die_attribute(self, die: DIE, attribute_name: str) -> None:
    die_id = id(die)
    if not die_id in self._parsed_die_attributes:
      self._parsed_die_attributes[die_id] = [attribute_name]
    else:
      self._parsed_die_attributes[die_id].append(attribute_name)
