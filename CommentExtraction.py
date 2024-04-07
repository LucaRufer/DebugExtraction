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

import re, os

from DWARFParser import TypeParser
from FileHandler import FileHandler, FileHandlerError

class CommentExporter:
  C_BLOCK_COMMENT_REGEX = re.compile(r"/\*+[ \t]*(.*?)\s*\*/", re.DOTALL)
  C_COMMENT_REGEX = re.compile(r"//.*")
  C_FILE_EXTENSIONS = (".h", ".c", ".hpp", ".cpp", ".cc")

  def __init__(self,
               fileHandler: FileHandler|None = None,
               attempt_substructure_extraction: bool = True
               ) -> None:
    self._parsed_file_contents: dict[str, str] = {}
    self._parsed_file_comments: dict[str, dict[int, tuple[str, int]]] = {}
    self._parsed_file_line_offsets: dict[str, list[int]] = {}
    self._skipped_files: set[str] = set()
    self.fileHandler = fileHandler
    self.attempt_substructure_extraction = attempt_substructure_extraction

  def get_comment(self, tag: TypeParser.AbstractTAG) -> tuple[str|None, str|None]|None:
    # Get the declaration file path, line and column
    if (declaration := self._get_declaration_from_TAG(tag)) is None:
      # The declaration is incomplete
      if self.attempt_substructure_extraction:
        return self._get_comment_from_containing_structure(tag)
      else:
        return None

    # Get the allowed keywords before the declaration
    allowed_keywords = self._get_allowed_keywords(type(tag))

    # Unpack declaration
    file_path, line, column = declaration

    # Extract the file context
    file_context = self._get_file_context(file_path)
    if file_context is None:
      return None
    content, comment_dict, line_offsets = file_context

    # Calculate the offset
    offset = line_offsets[line - 1] + column - 1

    # Extract and return the comments
    comment_before = self._get_comment_before(offset, comment_dict, line_offsets, content, allowed_keywords)
    comment_after = self._get_comment_after(offset, comment_dict, line_offsets, content)
    return comment_before, comment_after

  def _get_declaration_from_TAG(self, tag: TypeParser.AbstractTAG) -> tuple[str, int, int]|None:
    file_path, line, column = tag.decl.get_full_file_path(), tag.decl.line, tag.decl.column
    if file_path is None or line is None or column is None:
      return None
    return file_path, line, column

  def _get_comment_from_containing_structure(self, tag: TypeParser.AbstractTAG) -> tuple[str|None, str|None]|None:
    # Check if the TAG has is a substructure and if the containing structure is valid
    containing_structure = getattr(tag, "containing_structure", None)
    if containing_structure is None or not isinstance(containing_structure, TypeParser.AbstractTAG):
      return None

    # Extract and check declaration of the containing structure
    declaration = self._get_declaration_from_TAG(containing_structure)
    if declaration is None:
      return None
    file_path, line, column = declaration

    # Check that the TAG has a name
    if (name := tag.name) is None:
      return None

    # Get the allowed keywords before the declaration
    allowed_keywords = self._get_allowed_keywords(type(tag))

    # Extract the file content
    file_context = self._get_file_context(file_path)
    if file_context is None:
      return None
    content, comment_dict, line_offsets = file_context

    # Compute containing structure offset
    containing_structure_offset = line_offsets[line - 1] + column - 1

    # Find the first stand-alone occurrence of the name after
    for match_ in re.finditer(fr"\W{name}\W", content[containing_structure_offset:]):
      # Check that the match is not inside a comment
      match_start = match_.start() + containing_structure_offset
      match_end = match_.end() + containing_structure_offset
      if not self._is_offset_in_comment(match_start, match_end, comment_dict):
        break
    else:
      # No valid match found
      return None
    offset = match_start

    # Extract and return the comments
    comment_before = self._get_comment_before(offset, comment_dict, line_offsets, content, allowed_keywords)
    comment_after = self._get_comment_after(offset, comment_dict, line_offsets, content)
    return comment_before, comment_after

  def _get_file_context(self, file_path: str) -> tuple[str, dict[int, tuple[str, int]], list[int]]|None:

    # Check if the file is skipped due to some error
    if file_path in self._skipped_files:
      return None

    if file_path in self._parsed_file_contents:
      content = self._parsed_file_contents[file_path]
    else:
      # Read the file
      try:
        # Open the file
        if self.fileHandler:
          file = self.fileHandler.open(file_path, 'r')
        else:
          file = open(file_path, 'r')
        # Read the file
        content = file.read()
        # Close the file
        if not self.fileHandler:
          file.close()
      except Exception as e:
        print(f"[CommentExporter] Error while reading file '{file_path}': {e}")
        self._skipped_files.add(file_path)
        return None

    # Check if the files was already parsed
    if not file_path in self._parsed_file_contents:
      self._parsed_file_contents[file_path] = content
    if not file_path in self._parsed_file_comments:
      # Get the comments
      self._parsed_file_comments[file_path] = self._get_file_comments(content, file_path)
    if not file_path in self._parsed_file_line_offsets:
      # Create a list with line offsets
      line_lengths = [len(line) for line in content.splitlines(keepends=True)]
      line_offsets = [sum(line_lengths[:idx]) for idx in range(len(line_lengths))]
      self._parsed_file_line_offsets[file_path] = line_offsets

    # Get the comments and line offsets
    comment_dict = self._parsed_file_comments[file_path]
    line_offsets = self._parsed_file_line_offsets[file_path]

    return content, comment_dict, line_offsets

  def _get_comment_before(self,
                          offset: int,
                          comment_dict: dict[int, tuple[str, int]],
                          line_offsets: list[int],
                          content:str,
                          allowed_keywords: list[str]|None = None,
                          ) -> str|None:
    # Find all comment offsets before the offset. Return if no comments found
    comment_offsets = [key for key in comment_dict.keys() if key < offset]
    if len(comment_offsets) == 0:
      return None

    # Find the closest comment before the start of the declaration
    candidate_offset = max(comment_offsets)
    candidate, candidate_length = comment_dict[candidate_offset]

    # Find the text between the candidate comment and the declaration
    candidate_end = candidate_offset + candidate_length
    text_between_comment_and_decl = content[candidate_end:offset]

    # If some keywords are allowed, check if they occur directly in the last non-whitespace line
    if allowed_keywords is not None and len(allowed_keywords) > 0:
      keyword_test_text = text_between_comment_and_decl.rstrip()
      remaining_text, _, keyword_test_line = keyword_test_text.rpartition('\n')
      keyword_test_words = re.split(r"[ (){}[\]/*]", keyword_test_line)
      for keyword in allowed_keywords:
        if keyword in keyword_test_words:
          # The keyword was found, so the line is allowed and only the remaining text is checked
          text_between_comment_and_decl = remaining_text
          break

    # Check if the candidate is valid
    is_valid_candidate = True

    # Check if the candidate above the declaration
    if '\n' in text_between_comment_and_decl:
      text_above_decl, _, text_left_of_decl = text_between_comment_and_decl.rpartition('\n')
      # Only whitespace characters in the lines between the comment and the declaration
      is_valid_candidate &= text_above_decl.isspace() or len(text_above_decl) == 0

      # Check that the multiline comment has nothing before it on the same line
      closest_line_offset = max([lo for lo in line_offsets if lo <= candidate_offset])
      content_before_comment = content[closest_line_offset:candidate_offset]
      is_valid_candidate &= content_before_comment.isspace() or len(content_before_comment) == 0
    else:
      text_left_of_decl = text_between_comment_and_decl

    # Check that the content on the same line before the declaration does not contain certain characters
    is_valid_candidate &= (not ',' in text_left_of_decl) and (not ';' in text_left_of_decl)

    # If the candidate is valid, return the candidate
    if is_valid_candidate:
      return candidate
    else:
      return None

  def _get_comment_after(self,
                         offset: int,
                         comment_dict: dict[int, tuple[str, int]],
                         line_offsets: list[int],
                         content:str
                         ) -> str|None:
    # Find all comment offsets after the offset. Return if no comments found
    comment_offsets = [key for key in comment_dict.keys() if key >= offset]
    if len(comment_offsets) == 0:
      return None

    # Find the closest comment after the start of the declaration
    candidate_offset = min(comment_offsets)
    candidate, _ = comment_dict[candidate_offset]

    # Check if the candidate is valid
    is_valid_candidate = True

    # Find the text between the declaration and the candidate comment
    text_between_decl_and_comment = content[offset:candidate_offset]

    # Find the first occurrence of a delimiter symbol
    declaration_delimiters = (',', ';', '}', '{')
    delimiter_indexes = [text_between_decl_and_comment.find(delimiter) for delimiter in declaration_delimiters]
    delimiter_indexes = [idx for idx in delimiter_indexes if idx >= 0]
    if len(delimiter_indexes) == 0:
      # If no delimiter is present, assume declaration to end at the current line
      # In this case, the comment must be on the next line, with only spaces/tabs before the comment
      lines_below_decl = text_between_decl_and_comment.split('\n')[1:]
      is_valid_candidate &= len(lines_below_decl) == 0 or \
                            len(lines_below_decl) == 1 and (lines_below_decl[0].isspace() or len(lines_below_decl) == 0)
    else:
      after_decl_text = text_between_decl_and_comment[min(delimiter_indexes)+1:]
      if len(after_decl_text) > 0:
        # If there is text after the declaration, make sure it is only whitespaces and maximum one newline
        is_valid_candidate &= after_decl_text.isspace() and after_decl_text.count('\n') <= 1

    # If the candidate is valid, return the candidate
    if is_valid_candidate:
      return candidate
    else:
      return None

  def _get_file_comments(self, content: str, file_path: str) -> dict[int, tuple[str, int]]:
    file_base, extension = os.path.splitext(file_path)
    comments = {}
    if extension in self.C_FILE_EXTENSIONS:
      c_comment_list = self._get_c_block_comments(content) + self._get_c_comments(content)
      comments = {start : (comment, end - start) for comment, start, end in c_comment_list}
    elif len(extension) != 0:
      print(f"[CommentExporter] Error: Unknown comment structure for file with extension {extension} of {file_base}.")
    return comments

  def _get_allowed_keywords(self, tag_type: type[TypeParser.AbstractTAG]) -> list[str]|None:
    allowed_keywords = []
    if issubclass(tag_type, TypeParser.ClassType):
      allowed_keywords = ["class", "typedef"]
    if issubclass(tag_type, TypeParser.EnumerationType):
      allowed_keywords = ["enum", "typedef"]
    if issubclass(tag_type, TypeParser.StructureType):
      allowed_keywords = ["struct", "typedef"]
    if issubclass(tag_type, TypeParser.UnionType):
      allowed_keywords = ["union", "typedef"]
    if issubclass(tag_type, TypeParser.TypeDefType):
      allowed_keywords = ["typedef"]
    return allowed_keywords

  def _get_c_block_comments(self, content: str) -> list[tuple[str, int, int]]:
    comments: list[tuple[str, int, int]] = []
    for re_match in re.finditer(self.C_BLOCK_COMMENT_REGEX, content):
      start_index, end_index = re_match.span()
      # Remove any new lines starting with spaces and then a star
      comment = re.sub(r"\n\s*\*", "\n",  re_match.group(1))
      comments.append((comment, start_index, end_index))
    return comments

  def _get_c_comments(self, content: str) -> list[tuple[str, int, int]]:
    comments: list[tuple[str, int, int]] = []
    for re_match in re.finditer(self.C_COMMENT_REGEX, content):
      start_index, end_index = re_match.span()
      # Remove the // and any leading and trailing whitespaces
      comment = re_match.group()[2:].strip()
      comments.append((comment, start_index, end_index))
    return comments

  def _is_offset_in_comment(self, range_start: int, range_end: int, comment_dict: dict[int, tuple[str, int]]) -> bool:
    for key, value in comment_dict.items():
      # Comment start in range OR comment end in range OR range in comment
      if range_start <= key < range_end or \
         range_start < key + value[1] <= range_end or \
         key <= range_start < key + value[1]:
        return True
    return False
