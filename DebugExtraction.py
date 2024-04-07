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

import argparse
import elftools.dwarf.constants as DWARFConstants
import json
import os

from collections import deque
from DWARFParser import TypeParser
from CommentExtraction import CommentExporter
from datetime import datetime
from FileHandler import FileHandler, GithubFileHandler
from io import BytesIO
from typing import Union, Dict, List

JSONVal = Union[None, bool, str, float, int, 'JSONArray', 'JSONObject']
JSONArray = List[JSONVal]
JSONObject = Dict[str, JSONVal]

class DebugInfoExporter:

  EXPORTABLE_CLASSES: dict[str, type[TypeParser.AbstractTAG]] = {
    "BaseType"            : TypeParser.BaseType,
    "ClassType"           : TypeParser.ClassType,
    "EnumerationType"     : TypeParser.EnumerationType,
    "StructureType"       : TypeParser.StructureType,
    "SubroutineType"      : TypeParser.SubroutineType,
    "TypeDefType"         : TypeParser.TypeDefType,
    "UnionType"           : TypeParser.UnionType,
    "UnspecifiedType"     : TypeParser.UnspecifiedType,
    "Variable"            : TypeParser.Variable,
  }

  BASE_TYPE_ENCODING_DICT = {
    DWARFConstants.DW_ATE_void: "void",
    DWARFConstants.DW_ATE_address: "address",
    DWARFConstants.DW_ATE_boolean: "boolean",
    DWARFConstants.DW_ATE_complex_float: "complex float",
    DWARFConstants.DW_ATE_float: "float",
    DWARFConstants.DW_ATE_signed: "int",
    DWARFConstants.DW_ATE_signed_char: "char",
    DWARFConstants.DW_ATE_unsigned: "uint",
    DWARFConstants.DW_ATE_unsigned_char: "uchar",
    DWARFConstants.DW_ATE_imaginary_float: "imaginary float",
    DWARFConstants.DW_ATE_packed_decimal: "packed decimal",
    DWARFConstants.DW_ATE_numeric_string: "numerical string",
    DWARFConstants.DW_ATE_edited: "edited",
    DWARFConstants.DW_ATE_signed_fixed: "fixed",
    DWARFConstants.DW_ATE_unsigned_fixed: "ufixed",
    DWARFConstants.DW_ATE_decimal_float: "decimal float",
    DWARFConstants.DW_ATE_UTF: "UTF",
    DWARFConstants.DW_ATE_UCS: "UCS",
    DWARFConstants.DW_ATE_ASCII: "ASCII",
    None: "Unknown"
  }

  DEFAULT_EXPORT_CLASSES = (TypeParser.ClassType, TypeParser.EnumerationType, TypeParser.StructureType,
                            TypeParser.SubroutineType, TypeParser.UnionType, TypeParser.Variable)

  def _export_baseType(self,
                       baseType: TypeParser.BaseType,
                       unpack: bool,
                       mappings: set[TypeParser.AbstractTAG] = set()
                       ) -> JSONObject:
    desc = {}
    desc["datatype"] = self.BASE_TYPE_ENCODING_DICT[baseType.encoding]
    if unpack and baseType.name is not None:
      desc["name"] = baseType.name
    desc["datawidth"] = baseType.byte_size()
    return desc
  
  def _export_unspecifiedType(self,
                              unspecifiedType: TypeParser.UnspecifiedType,
                              unpack: bool,
                              mappings: set[TypeParser.AbstractTAG] = set()
                              ) -> JSONObject:
    desc = {}
    desc["datatype"] = "unspecified"
    desc["name"] = unspecifiedType.name
    return desc

  def _export_typeDefType(self,
                          typeDefType: TypeParser.TypeDefType,
                          unpack: bool,
                          mappings: set[TypeParser.AbstractTAG] = set()
                          ) -> JSONObject:
    desc = {}
    if unpack:
      desc["datatype"] = "typedef"
      desc["name"] = typeDefType.name
      if typeDefType.type in mappings:
        desc["mapping"] = typeDefType.type.name
      else:
        desc["type"] = self._export_type(typeDefType.type, unpack, mappings)
    else:
      if typeDefType in mappings:
        desc["datatype"] = "typedef"
        desc["mapping"] = typeDefType.get_name()
      else:
        desc.update(self._export_type(typeDefType.type, False, mappings))
    return desc

  def _export_member(self,
                     member: TypeParser.Member,
                     mappings: set[TypeParser.AbstractTAG] = set()
                     ) -> JSONObject:
    desc: JSONObject = {}
    if member.name is not None:
      desc["identifier"] = member.name

    if member.type is not None:
      if member.type in mappings and (member_type_name := member.type.get_name()) is not None:
        desc["mapping"] = member_type_name
      else:
        desc.update(self._export_type(member.type, False, mappings))

    if (member_width := member.byte_size()) is not None:
      desc["datawidth"] = member_width
    if member.bit_size:
      desc["bit_size"] = member.bit_size

    member_offset = member.get_offset()
    if member_offset is not None:
      byte_offset, bit_offset = member_offset
      desc["byte_offset"] = byte_offset
      if bit_offset:
        desc["bit_offset"] = bit_offset

    # Export comments
    if self.export_comments:
      desc.update(self._export_comments(member))
    return desc

  def _export_structure(self,
                        structure: TypeParser.StructureType,
                        unpack: bool,
                        mappings: set[TypeParser.AbstractTAG] = set()
                        ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "struct"
    structure_name = structure.get_name()
    structure_size = structure.byte_size()
    if structure_size is not None:
      desc["datawidth"] = structure_size
    if unpack or not structure in mappings or structure_name is None:
      if structure_name is not None:
        desc["name"] = structure_name
      desc["members"] = [self._export_member(member, mappings) for member in structure.members]
    else:
      desc["mapping"] = structure_name
    return desc

  def _export_union(self,
                    union: TypeParser.UnionType,
                    unpack: bool,
                    mappings: set[TypeParser.AbstractTAG] = set()
                    ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "union"
    union_name = union.get_name()
    union_size = union.byte_size()
    if union_size is not None:
      desc["datawidth"] = union_size
    if unpack or not union in mappings or union_name is None:
      if union_name is not None:
        desc["name"] = union_name
      desc["members"] = [self._export_member(member, mappings) for member in union.members]
    else:
      desc["mapping"] = union_name
    return desc

  def _export_class(self,
                    class_: TypeParser.ClassType,
                    unpack: bool,
                    mappings: set[TypeParser.AbstractTAG] = set()
                    ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "class"
    class_name = class_.get_name()
    class_size = class_.byte_size()
    if class_size is not None:
      desc["datawidth"] = class_size
    if unpack or not class_ in mappings or class_name is None:
      if class_name is not None:
        desc["name"] = class_name
      desc["members"] = [self._export_member(member, mappings) for member in class_.members]
    else:
      desc["mapping"] = class_name
    return desc

  def _export_enumerator(self,
                         enumerator: TypeParser.Enumerator,
                         mappings: set[TypeParser.AbstractTAG] = set()
                         ) -> JSONObject:
    desc: JSONObject = {}
    desc["value"] = enumerator.value
    desc["representation"] = enumerator.name

    # Export comments
    if self.export_comments:
      desc.update(self._export_comments(enumerator))
    return desc

  def _export_enumeration(self,
                          enumeration: TypeParser.EnumerationType,
                          unpack: bool,
                          mappings: set[TypeParser.AbstractTAG] = set()
                          ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "enumeration"
    if (enumeration_size := enumeration.byte_size()) != None:
      desc["datawidth"] = enumeration_size
    enumeration_name = enumeration.get_name()
    if unpack or not enumeration in mappings:
      if enumeration_name is not None:
        desc["name"] = enumeration_name
      if enumeration.encoding is not None and enumeration.encoding in self.BASE_TYPE_ENCODING_DICT:
        desc["encoding"] = self.BASE_TYPE_ENCODING_DICT[enumeration.encoding]
      if (not "datawidth" in desc or not "encoding" in desc) and enumeration.type is not None:
        desc["type"] = self._export_type(enumeration.type, False, mappings)
      desc["enumerators"] = [self._export_enumerator(enumerator, mappings)
                             for enumerator in enumeration.enumerators
                             if isinstance(enumerator, TypeParser.Enumerator)]
    else:
      if enumeration_name is not None:
        desc["mapping"] = enumeration_name
    return desc

  def _export_pointer(self,
                      pointer: TypeParser.PointerType,
                      mappings: set[TypeParser.AbstractTAG] = set()
                      ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "pointer"
    desc["datawidth"] = pointer.byte_size()
    if pointer.type is not None:
      pointed_type = self._trace_next_mapped_type(pointer.type, mappings)
      if pointed_type is not None:
        pointed_type_name = pointed_type.get_name()
        if pointed_type_name is not None:
          desc["mapping"] = pointed_type_name
      else:
        desc["type"] = self._export_type(pointer.type, False, mappings)
    return desc

  def _export_reference(self,
                        reference: TypeParser.ReferenceType,
                        mappings: set[TypeParser.AbstractTAG] = set()
                        ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "reference"
    desc["datawidth"] = reference.byte_size()
    if reference.type is not None:
      referenced_type = self._trace_next_mapped_type(reference.type, mappings)
      if referenced_type is not None:
        referenced_type_name = referenced_type.get_name()
        if referenced_type_name is not None:
          desc["mapping"] = referenced_type_name
      else:
        desc["type"] = self._export_type(reference.type, False, mappings)
    return desc

  def _export_array(self,
                    array: TypeParser.ArrayType,
                    mappings: set[TypeParser.AbstractTAG] = set()
                    ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "array"
    desc["dimensions"] = [d.count for d in array.get_dimensions() if d is not None]
    if array.byte_stride:
      desc["stride"] = array.byte_stride
    desc["type"] = self._export_type(array.type, False, mappings)
    return desc

  def _export_parameter(self,
                        parameter: TypeParser.FormalParameter,
                        mappings: set[TypeParser.AbstractTAG] = set()
                        ) -> JSONObject:
    desc: JSONObject = {}
    if parameter.name is not None:
      desc["identifier"] = parameter.name
    if parameter.type is not None:
      desc["type"] = self._export_type(parameter.type, False, mappings)
    return desc

  def _export_subroutine(self,
                         subroutine: TypeParser.SubroutineType,
                         mappings: set[TypeParser.AbstractTAG] = set()
                         ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "subroutine"
    subroutine_name = subroutine.get_name()
    if subroutine_name is not None:
      desc["name"] = subroutine_name
    if subroutine.type is not None:
      desc["type"] = self._export_type(subroutine.type, False, mappings)
    desc["parameters"] = [self._export_parameter(p, mappings)
                          for p in subroutine.parameters
                          if isinstance(p, TypeParser.FormalParameter)]
    return desc

  def _export_variable(self,
                       variable: TypeParser.Variable,
                       mappings: set[TypeParser.AbstractTAG] = set()
                       ) -> JSONObject:
    desc: JSONObject = {}
    desc["datatype"] = "variable"
    variable_type = variable.get_type()
    variable_name = variable.get_name()
    variable_location = variable.get_location()
    if variable_name is not None:
      desc["name"] = variable_name
    if variable_type is not None:
      desc["type"] = self._export_type(variable_type, False, mappings)
    if variable_location is not None:
      desc["location"] = variable_location
    return desc

  def _export_void_type(self) -> JSONObject:
    desc: JSONObject = {}
    desc["datawidth"] = 0
    return desc

  def _export_comments(self, tag: TypeParser.AbstractTAG) -> JSONObject:
    desc = {}
    comments = self.commentExporter.get_comment(tag)
    if comments is not None:
      comment_before, comment_after = comments
      if comment_before is not None and comment_after is not None:
        desc["commentBefore"] = comment_before.strip()
        desc["commentAfter"] = comment_after.strip()
      elif comment_before is not None and comment_after is None:
        desc["comment"] = comment_before.strip()
      elif comment_before is None and comment_after is not None:
        desc["comment"] = comment_after.strip()
    return desc

  def _export_type(self,
                   type: TypeParser.AbstractTAG,
                   unpack: bool = True,
                   mappings: set[TypeParser.AbstractTAG] = set()
                   ) -> JSONObject:
    if type is None:
      raise Exception("Cannot Export 'none' type.")
    desc: JSONObject = {}
    if isinstance(type, TypeParser.BaseType):
      desc = self._export_baseType(type, unpack, mappings)
    elif isinstance(type, TypeParser.UnspecifiedType):
      desc = self._export_unspecifiedType(type, unpack, mappings)
    elif isinstance(type, TypeParser.TypeDefType):
      desc = self._export_typeDefType(type, unpack, mappings)
    elif isinstance(type, TypeParser.StructureUnionClassAbstractType):
      if isinstance(type, TypeParser.StructureType):
        desc = self._export_structure(type, unpack, mappings)
      elif isinstance(type, TypeParser.UnionType):
        desc = self._export_union(type, unpack, mappings)
      elif isinstance(type, TypeParser.ClassType):
        desc = self._export_class(type, unpack, mappings)
      else:
        raise Exception(f"Type {type.__class__.__name__} of {type.name} has no known export pattern.")
    elif isinstance(type, TypeParser.EnumerationType):
      desc = self._export_enumeration(type, unpack, mappings)
    elif isinstance(type, TypeParser.AbstractModifierType):
      if isinstance(type, TypeParser.PointerType):
        desc = self._export_pointer(type, mappings)
      elif isinstance(type, TypeParser.ReferenceType):
        desc = self._export_reference(type, mappings)
      elif isinstance(type, (TypeParser.AtomicType, TypeParser.ConstType, TypeParser.ImmutableType,
                             TypeParser.PackedType, TypeParser.RestrictType, TypeParser.RValueReferenceType,
                             TypeParser.SharedType, TypeParser.VolatileType)):
        if type.type is None:
          desc = self._export_void_type()
        else:
          desc = self._export_type(type.type, unpack, mappings)
      else:
        raise Exception(f"Type {type.__class__.__name__} of {type.name} has no known export pattern.")
    elif isinstance(type, TypeParser.ArrayType):
      desc = self._export_array(type, mappings)
    elif isinstance(type, TypeParser.SubroutineType):
      desc = self._export_subroutine(type, mappings)
    elif isinstance(type, TypeParser.Variable):
      desc = self._export_variable(type, mappings)
    else:
      raise Exception(f"Type {type.__class__.__name__} of {type.name} has no known export pattern.")

    # Export comments
    if self.export_comments and unpack:
      desc.update(self._export_comments(type))
    return desc

  def export_all(self, **kwargs) -> list[dict]:
    return self.export_specific_classes(list(self.EXPORTABLE_CLASSES.values()), **kwargs)

  def export_specific_classes(self, export_classes: list[type[TypeParser.AbstractTAG]], **kwargs) -> list[dict]:
    types_to_export: list[TypeParser.AbstractTAG] = []
    for cls in export_classes:
      types_to_export.extend(self.typeParser.get_types_by_class(cls))
    return self._export_types(list(types_to_export), **kwargs)

  def export_named_types(self,
                         export_type_names: list[str],
                         unpack_StructureUnionClass_typedefs: bool = True,
                         **kwargs
                         ) -> list[dict]:
    # Convert names to types
    types_to_export: list[TypeParser.AbstractTAG] = []
    for type_name in export_type_names:
      name_matches = self.typeParser.get_type_by_name(type_name)
      if len(name_matches) == 0:
        raise Exception(f"Type {type_name} not found.")
      if len(name_matches) > 1:
        print(f"""DebugExtraction] Warning: Found {len(name_matches)} types named '{type_name}'.
                  Exporting only the first match.""")
      type_to_export = name_matches[0]

      # Unpack typedefs if the corresponding option is set
      if unpack_StructureUnionClass_typedefs and isinstance(type_to_export, TypeParser.TypeDefType):
        unpack_candidate = type_to_export.type
        while isinstance(unpack_candidate, TypeParser.TypeDefType):
          unpack_candidate = unpack_candidate.type
        if isinstance(unpack_candidate, TypeParser.StructureUnionClassAbstractType) and \
           unpack_candidate.get_name() is not None:
          type_to_export = unpack_candidate

      # Add the type to be exported
      types_to_export.append(type_to_export)
    return self._export_types(types_to_export, **kwargs)

  def _export_types(self,
                    types: list[TypeParser.AbstractTAG],
                    export_dependencies = True,
                    export_classes: tuple[type[TypeParser.AbstractTAG],...]|None = None,
                    export_completed_declarations = True,
                    export_unnamed = False,
                    ) -> list[dict]:
    if export_classes is None:
        export_classes = self.DEFAULT_EXPORT_CLASSES

    # Determine the dependencies of the types to be extracted:
    if export_dependencies:
      # Keep a set for uniqueness and a list for deterministic order
      dependencies: list[TypeParser.AbstractTAG] = []
      dependencies_set: set[TypeParser.AbstractTAG] = set(types)
      for type in types:
        type_dependencies = type.get_type_dependencies()
        for dep in type_dependencies:
          if not dep in dependencies_set:
            dependencies_set.add(dep)
            dependencies.append(dep)

      # Filter only selected classes
      n_removed = 0
      if len(export_classes) > 0:
        n_deps = len(dependencies)
        dependencies = [type for type in dependencies if isinstance(type, export_classes)]
        n_removed = n_deps - len(dependencies)
      types_to_export = types + dependencies
      print(f"[DebugExtraction] Info: Included {len(dependencies)} additional dependencies.")
      if n_removed > 0:
        print(f"[DebugExtraction] Info: {n_removed} dependencies are not included because of their class.")
    else:
      types_to_export = types

    # If export_completed_declarations, replace declarations with their completed version
    if export_completed_declarations:
      replacements: deque[tuple[int, TypeParser.AbstractTAG|None]] = deque()
      n_removed, n_replaced, n_duplicate = (0, 0, 0)
      for idx, type in enumerate(types_to_export):
        if isinstance(type, TypeParser.Declarable) and type.declaration:
          replacements.appendleft((idx, type.completed_TAG))
      for idx, replacement in replacements:
        if replacement is None:
          if replacement in types_to_export: n_duplicate += 1
          else: n_removed += 1
          types_to_export.pop(idx)
        else:
          types_to_export[idx] = replacement
          n_replaced += 1
      if n_replaced > 0:
        print(f"[DebugExtraction] Info: replaced {n_replaced} declarations with their completion.")
      if n_removed > 0:
        print(f"[DebugExtraction] Info: removed {n_removed} non-defining declarations without a replacement.")
      if n_duplicate > 0:
        print(f"[DebugExtraction] Info: removed {n_duplicate} declarations where the completion is already exported.")

    # Check if unnamed descriptions are to be exported
    if not export_unnamed:
      n_tot = len(types_to_export)
      types_to_export = [type for type in types_to_export if type.get_name() is not None]
      n_unnamed = n_tot - len(types_to_export)
      print(f"[DebugExtraction] Info: removed {n_unnamed} types that have no name.")

    # Remove typedefTypes if the type they refer to is already included and the referenced type itself is not named
    duplicate_typedefs: set[TypeParser.TypeDefType] = set()
    types_to_export_ids = set([id(type) for type in types_to_export])
    for type in types_to_export:
      if isinstance(type, TypeParser.TypeDefType) and id(type.type) in types_to_export_ids:
        duplicate_typedefs.add(type)
    n_dup = len(duplicate_typedefs)
    if n_dup > 0:
      types_to_export = [type for type in types_to_export if not type in duplicate_typedefs]
      print(f"[DebugExtraction] Info: removed {n_dup} typedefs as the type they refer to will be exported.")

    # Export the types
    types_to_export_set: set[TypeParser.AbstractTAG] = set(types_to_export)
    type_descriptions: list[dict] = []
    failed_exports: list[TypeParser.AbstractTAG] = []
    export_stats: dict[type[TypeParser.AbstractTAG], int] = {}
    export_failed_stats: dict[type[TypeParser.AbstractTAG], int] = {}
    for type in types_to_export:
      desc = None
      if self.skip_errors:
        # Export using try/except to catch, print and than skip errors
        try:
          desc = self._export_type(type, mappings = types_to_export_set)
        except Exception as e:
          failed_exports.append(type)
          cls_name = type.__class__.__name__
          if type.name is not None:
            failure_description = f"type {type.name} of class {cls_name}"
          elif type.get_name() is not None:
            failure_description = f"unnamed type (known as {type.get_name()}) of class {cls_name}"
          elif type.decl.file_name is not None:
            failure_description = f"unnamed type of class {cls_name} declared in {type.decl.file_name}:{type.decl.column}"
          else:
            failure_description = f"unnamed type of unknown origin of class {cls_name}"
          print(f"[DebugExtraction] Error: Failed to export {failure_description}: {e}")

      else:
        # Fail when a type cannot be exported
        desc = self._export_type(type, mappings = types_to_export_set)

      if desc is not None:
        type_descriptions.append(desc)
        export_stats[type.__class__] = export_stats.get(type.__class__, 0) + 1
      else:
        export_failed_stats[type.__class__] = export_failed_stats.get(type.__class__, 0) + 1

    # Print export stats
    n_exported = sum(export_stats.values())
    print(f"[DebugExtraction] Info: Exported {n_exported} types{':' if n_exported else '.'}")
    for cls, cnt in export_stats.items():
      print(f"{str(cnt).rjust(6)} {cls.__name__}")
    n_export_failed = sum(export_failed_stats.values())
    if n_export_failed > 0:
      print(f"[DebugExtraction] Info: Failed to export {n_export_failed} types{':' if n_export_failed else '.'}")
      for cls, cnt in export_failed_stats.items():
        print(f"{str(cnt).rjust(6)} {cls.__name__}")

    # Remove duplicates
    duplicate_indexes: list[int] = []
    for idx, desc in enumerate(type_descriptions):
      for desc_2 in type_descriptions[idx+1:]:
        if desc == desc_2:
          duplicate_indexes.append(idx)
          break
    if len(duplicate_indexes) > 0:
      print(f"[DebugExtraction] Info: Removing {len(duplicate_indexes)} duplicate type descriptions.")
      duplicate_indexes.reverse()
      for idx in duplicate_indexes:
        type_descriptions.pop(idx)

    return type_descriptions

  def validate_export(self, type_descriptions: list[JSONObject]):
    # Check for duplicate names
    name_duplicate_count: dict[str, int] = {}
    for desc in type_descriptions:
      if "name" in desc:
        name = str(desc["name"])
        if name in name_duplicate_count:
          name_duplicate_count[name] += 1
        else:
          name_duplicate_count[name] = 0
    name_duplicate_count = {name:count for name, count in name_duplicate_count.items() if count > 0}
    # Print duplicate names
    if len(name_duplicate_count) > 0:
      print(f"[DebugExtraction] Info: Found {len(name_duplicate_count)} description(s) with duplicate names:")
      max_str_len = max([len(name) for name in name_duplicate_count])
      count_digits = len(str(max(name_duplicate_count.values())))
      for name, count in name_duplicate_count.items():
        print(f" - {name.ljust(max_str_len)}: {str(count + 1).rjust(count_digits)} duplicates")

    # Check for 'None's (null in JSON)
    paths_to_None: list[tuple[str, list[list[str|int]]]] = []
    for desc in type_descriptions:
      paths_to_None.append((str(desc["name"]), self._check_JSONObject_for_None(desc)))
    total_paths_to_None = sum([len(paths) for _, paths in paths_to_None])
    # Print 'None's in descriptions
    if total_paths_to_None > 0:
      print(f"[DebugExtraction] Warning: Found {total_paths_to_None} description(s) with a 'None' entry:")
    for name, paths in paths_to_None:
      for path in paths:
        path_desc = ""
        for path_elem in path:
          if isinstance(path_elem, str):
            path_desc += path_elem if path_desc == "" else " -> " + path_elem
          else:
            path_desc += "[" + str(path_elem) + "]"
        print(f" - Entry named {name}: {path_desc}")

    # Check if all referenced mappings are exported
    exported_mappings: set[str] = set()
    referenced_mappings: set[str] = set()
    for desc in type_descriptions:
      mapping_matches = self._filter_JSONObject_values(desc, "mapping")
      referenced_mappings.update([ref for ref in mapping_matches if isinstance(ref, str)])
      if "name" in desc:
        exported_mappings.add(str(desc["name"]))
    missing_mappings = referenced_mappings.difference(exported_mappings)
    # Print missing mappings
    if len(missing_mappings) > 0:
      print(f"[DebugExtraction] Warning: Found {len(missing_mappings)} mapping(s) that are referenced but not exported:")
    for missing_mapping in missing_mappings:
      print(f" - {missing_mapping}")

  def _check_JSONObject_for_None(self, desc: JSONObject) -> list[list[str|int]]:
    paths_to_None: list[list[str|int]] = []
    for keyword, value in desc.items():
      sub_paths_to_None = self._check_JSONVal_for_None(value)
      paths_to_None.extend([[keyword] + sub_path for sub_path in sub_paths_to_None])
    return paths_to_None

  def _check_JSONArray_for_None(self, array: JSONArray) -> list[list[str|int]]:
    paths_to_None: list[list[str|int]] = []
    for idx, obj in enumerate(array):
      sub_paths_to_None = self._check_JSONVal_for_None(obj)
      paths_to_None.extend([[idx] + sub_path for sub_path in sub_paths_to_None])
    return paths_to_None

  def _check_JSONVal_for_None(self, value: JSONVal) -> list[list[str|int]]:
    if value is None:
      return [[]]
    elif isinstance(value, (bool, str, float, int)):
      return []
    elif isinstance(value, list):
      return self._check_JSONArray_for_None(value)
    elif isinstance(value, dict):
      return self._check_JSONObject_for_None(value)
    else:
      raise Exception(f"Unknown JSON value class '{value.__class__.__name__}': {value}")

  def _filter_JSONObject_values(self, object: JSONObject, filter_value: JSONVal) -> list[JSONVal]:
    matches: list[JSONVal] = []
    if filter_value in object:
      matches.append(object[filter_value])
    for value in object.values():
      matches.extend(self._filter_JSONVal_values(value, filter_value))
    return matches

  def _filter_JSONArray_values(self, array: JSONArray, filter_value: JSONVal) -> list[JSONVal]:
    matches: list[JSONVal] = []
    for value in array:
      matches.extend(self._filter_JSONVal_values(value, filter_value))
    return matches

  def _filter_JSONVal_values(self, value: JSONVal, filter_value: JSONVal) -> list[JSONVal]:
    if value is None:
      return []
    elif isinstance(value, (bool, str, float, int)):
      return []
    elif isinstance(value, list):
      return self._filter_JSONArray_values(value, filter_value)
    elif isinstance(value, dict):
      return self._filter_JSONObject_values(value, filter_value)
    else:
      raise Exception(f"Unknown JSON value class '{value.__class__.__name__}': {value}")

  def _trace_next_mapped_type(self,
                              tag: TypeParser.AbstractTAG,
                              mappings: set[TypeParser.AbstractTAG]
                              ) -> TypeParser.AbstractTAG|None:
    if tag in mappings:
      return tag
    if isinstance(tag, TypeParser.Typed) and tag.type is not None:
      return self._trace_next_mapped_type(tag.type, mappings)
    return None

  def __init__(self,
               elf_file: BytesIO|str,
               skip_errors: bool = True,
               export_comments: bool = True,
               fileHandler: FileHandler|None = None,
               elf_file_modification_time: datetime|None = None,
               type_names: None|list[str] = None,
               ) -> None:
    self.skip_errors = skip_errors
    self.export_comments = export_comments

    self.fileHandler = fileHandler if fileHandler is not None else FileHandler()
    if isinstance(elf_file, str):
      self.fileHandler.enable_modification_warning(elf_file)
    if elf_file_modification_time:
      self.fileHandler.enable_modification_warning(elf_file_modification_time)

    self.commentExporter = CommentExporter(self.fileHandler)
    self.typeParser = TypeParser(elf_file,
                                 allow_duplicates=False,
                                 catch_exceptions=skip_errors,
                                 type_names = type_names)

def main():
  # Parse the arguments
  parser = argparse.ArgumentParser(description = __doc__)
  export_parser = argparse.ArgumentParser(add_help=False)

  # Export selection
  parser_export_group = export_parser.add_mutually_exclusive_group(required=True)
  parser_export_group.add_argument('-a', '--all', action='store_true',
                                   help='Export all parsed types.')
  parser_export_group.add_argument('-c', '--class', action="extend", nargs="+", type=str, default=[], dest="classes",
                                   choices=DebugInfoExporter.EXPORTABLE_CLASSES,
                                   help="""Classes(s) to be exported. All types of the selected classes will be exported.
                                           May be stated multiple times.""")
  parser_export_group.add_argument('-t', '--type', action="extend", nargs="+", type=str, default=[], dest="types",
                                   help='Name(s) of the Type(s) to be exported. May be stated multiple times.')

  # Export options
  export_parser.add_argument('-o', '--output', default='export.json',
                             help='Output file. Defaults to export.json')
  export_parser.add_argument(      '--skip-errors', action='store_true', default=False,
                             help="""Skip errors that occur during parsing and exporting.
                                     Errors that occur while parsing or exporting are printed to the console.""")
  export_parser.add_argument(      '--include-unnamed', action='store_true', default=False,
                             help="""Export types without an associated name like anonymous (or unused) enumerations, structs
                                     and unions and function declarations.""")
  export_parser.add_argument(      '--export-comments', action='store_true', default=False,
                             help="""Export comments from the source files of the types.""")
  export_parser.add_argument(      '--source-path-subst', nargs=2, action='extend', default=[],
                             help="""Usage: --source-path-subst <build/dir> <source/dir>
                                     Replace part of the extracted source paths with the actual source dir.
                                     Useful when the compiler was called with a relative path from the build directory.
                                     Can be stated multiple times""")

  # Add the subparsers
  subparsers = parser.add_subparsers(title="Source", dest="source",
                                     description="Select the source of the Debug information file(s).")
  local_parser = subparsers.add_parser('local', allow_abbrev=True, parents=[export_parser],
                                       help="""Extract the debug information from local files""")
  github_parser = subparsers.add_parser('github', allow_abbrev=True, parents=[export_parser],
                                        help="""Extract the debug information from a Github Repository""")

  # Local parser arguments
  local_parser.add_argument('ELFfile',
                            help='Executable File used for debug information extraction (.elf File)')

  # Github parser arguments
  github_parser.add_argument('repository',
                             help="""The name of the repository. Should be in the format [OWNER]/[REPO]""")
  github_parser.add_argument('ELFfile',
                             help="""Executable File used for debug information extraction (.elf File).""")
  github_parser.add_argument('--branch', default=None,
                             help="""Select a branch from which to extract the debug information.""")
  github_parser.add_argument('--from-artifact', nargs=2,
                             help="""Load the ELF file from an artifact.
                                  Use as --from-artifact ACTION-NAME ARTIFACT-NAME,
                                  Where 'ACTION-NAME' is the run name of the Action that produces the argument,
                                  and 'ARTIFACT-NAME' is the name of the Artifact itself.
                                  If the '--from-artifact' option is specified, the ELFfile argument specifies the
                                  file name of the ELF file within the artifact.
                                  Note: The --auth-token-file option is required to download artifacts.""")
  github_parser.add_argument('--auth-token-file', default=None,
                             help="""The path to a file containing the Github Authentication Token. For more details on
                                     authentication, see: https://docs.github.com/en/rest/authentication
                                     If this option is not used, the user will be asked to authenticate using a
                                     username and password""")

  # Parse the arguments
  args = parser.parse_args()

  # Convert the common arguments
  export_all = args.all
  export_classes = [DebugInfoExporter.EXPORTABLE_CLASSES[str(class_name)] for class_name in args.classes]
  export_types = args.types
  output_file = args.output
  skip_errors = args.skip_errors
  export_comments = args.export_comments
  include_unnamed = args.include_unnamed
  source_path_subst = list(zip(args.source_path_subst[::2], args.source_path_subst[1::2]))

  # Type names
  if len(export_types) == 0:
    export_types = None

  # Check source
  if args.source == "local":
    # Extract ELF file path
    elf_file = args.ELFfile
    elf_file_modification_time = None
    fileHandler = FileHandler()
  elif args.source == "github":
    # Load Authentication token
    if args.auth_token_file is not None:
      args.auth_token_file = os.path.expanduser(args.auth_token_file)
      with open(args.auth_token_file, 'r') as token_file:
        token = token_file.readline().strip()
    else:
      token = None
    # Create a Filehandler for Github files
    fileHandler = GithubFileHandler(args.repository, branch = args.branch, token=token)
    action_name, artifact_name = args.from_artifact
    elf_file, elf_file_modification_time = fileHandler.open_artifact(action_name, artifact_name, args.ELFfile)
  else:
    raise Exception(f"[DebugExtraction] Illegal source option: '{args.source}'")

  # Add the path substitution to the file handler
  fileHandler.substitute_paths(source_path_subst)

  # Create a debug info extractor from the given ELF file
  debugInfoExporter = DebugInfoExporter(elf_file=elf_file,
                                        skip_errors=skip_errors,
                                        export_comments=export_comments,
                                        fileHandler = fileHandler,
                                        elf_file_modification_time=elf_file_modification_time,
                                        type_names = export_types)

  # Exporting keyword arguments
  export_kw_args = {
    "export_unnamed": include_unnamed,
    "export_dependencies": True
  }

  if export_all:
    type_descriptions = debugInfoExporter.export_all(**export_kw_args)
  elif len(export_classes) > 0:
    type_descriptions = debugInfoExporter.export_specific_classes(export_classes, **export_kw_args)
  else:
    type_descriptions = debugInfoExporter.export_named_types(export_types, **export_kw_args)

  # Validate before exporting
  debugInfoExporter.validate_export(type_descriptions)

  # Export into the output file
  with open(output_file, 'w') as export_file:
    json.dump(type_descriptions, export_file, indent=2)

  print(f"[DebugExtraction] Info: Stored exported types in '{output_file}'")

if __name__ == "__main__":
  main()