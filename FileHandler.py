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

from datetime import datetime, timezone
from github import Github
from github import Auth
import io
import json
import os
import requests
from typing import IO, Any
import zipfile

class FileHandlerError(Exception):
  pass

class FileHandler:
  def __init__(self) -> None:
    # Initialize variables
    self._source_path_subst: list[tuple[str, str]] = []
    self._modification_warning: None|datetime = None
    self._modification_warning_issued: set[Any] = set()

  # A wrapper for the built-in 'open' function that checks and modifies file paths first
  def open(self,
           file: str,
           mode: str = "r",
           **kwargs) -> IO[Any]:

    # Process the file path
    file = self._process_path(file)

    # Check if the file exists
    if not os.path.isfile(file):
      raise(FileHandlerError(f"File {file} does not exist."))

    # Check the modification time
    modification_time_seconds = os.path.getmtime(file)
    modification_time = datetime.utcfromtimestamp(modification_time_seconds)
    modification_time = modification_time.replace(tzinfo=timezone.utc)
    self._check_modification_warning(file, modification_time)

    return open(file, mode, **kwargs)

  def substitute_path(self, path: str, subst: str) -> None:
    path = os.path.realpath(path)
    subst = os.path.realpath(subst)
    self._source_path_subst.append((path, subst))

  def substitute_paths(self, paths: list[tuple[str, str]]) -> None:
    for path, subst in paths:
      self.substitute_path(path, subst)

  def enable_modification_warning(self, reference: str|datetime):
    modification_time:datetime|None = None
    if isinstance(reference, str):
      if os.path.isfile(reference) or os.path.isdir(reference):
        modification_time_seconds = os.path.getmtime(reference)
        modification_time = datetime.utcfromtimestamp(modification_time_seconds)
        modification_time = modification_time.replace(tzinfo=timezone.utc)

    elif isinstance(reference, datetime):
      modification_time = reference

    if modification_time is not None:
      if self._modification_warning is None:
        self._modification_warning = modification_time
      else:
        self._modification_warning = min(self._modification_warning, modification_time)


  def _process_path(self, path: str) -> str:
    # Substitute the file path if necessary. Only the first match will be replaced
    path = os.path.realpath(path)
    for path_pattern, path_replacement in self._source_path_subst:
      if path_pattern in path:
        pre, _, post = path.rpartition(path_pattern)
        path = pre + path_replacement + post
        break

    # Return the processed path
    return path

  def _check_modification_warning(self, file: Any, modification_time: datetime) -> None:
    # If modification time checking is enabled, check that the file was not modified
    if self._modification_warning is not None and not file in self._modification_warning_issued:
      if modification_time > self._modification_warning:
        print(f"[FileHandler] Warning: File '{file}' was modified after the reference date")
        self._modification_warning_issued.add(file)

class GithubFileHandler(FileHandler):

  def __init__(self, repo: str, branch: str|None = None, token: str|None = None) -> None:
    super().__init__()

    # Check if a token exists
    if token is not None:
      self.auth = Auth.Token(token)
    else:
      print("[GithubFileHandler] Login using Username and Password.")
      username = input("Enter Username: ")
      password = input("Enter Password: ")
      self.auth = Auth.Login(username, password)

    self.github = Github(auth=self.auth)
    self.repo = self.github.get_repo(repo)
    self.branch = branch

  # A wrapper for the built-in 'open' function that checks and modifies file paths first
  def open(self,
           file: str,
           mode: str = "r",
           **kwargs) -> IO[Any]:

    # Process the file path
    file = self._process_path(file)

    # Check the mode
    if 'w' in mode or 'x' in mode or 'a' in mode or '+' in mode:
      raise FileHandlerError(f"Cannot open file '{file}' in mode '{mode}'. Github file handler only supports reading files.")

    # Get the file contents
    print(f"[GithubFileHandler] Downloading '{file}' from Github... ", end="")
    if self.branch is None:
      contentfile = self.repo.get_contents(file)
    else:
      contentfile = self.repo.get_contents(file, self.branch)
    print("Complete.")

    # Check if multiple files were returned
    if isinstance(contentfile, list):
      raise FileHandlerError(f"Cannot open list of files. Opening '{file}' returned {len(contentfile)} files.")

    # Check the modification time
    if contentfile.last_modified_datetime is not None:
      self._check_modification_warning(file, contentfile.last_modified_datetime)

    if 'b' in mode:
      # Return as Bytes
      return io.BytesIO(contentfile.decoded_content)
    else:
      # Return as Text
      return io.TextIOWrapper(io.BytesIO(contentfile.decoded_content))

  def open_artifact(self, run_name: str, artifact_name: str, file_name: str) -> tuple[io.BytesIO, datetime]:
    # Get a list of successful workflow runs
    if self.branch:
      branch = self.repo.get_branch(self.branch)
      runs = self.repo.get_workflow_runs(branch=branch, status="success")
    else:
      runs = self.repo.get_workflow_runs(status="success")

    # Keep track of all found artifacts
    found_artifacts: set[str] = set()

    # Iterate over the runs
    success = False
    for run in runs:
      # Check the run name
      if run.raw_data['name'] == run_name:
        status, headers, artifacts = run._requester.requestJson("GET", run.artifacts_url)
        # Continue on with the next run in case of an error
        if status > 400:
          continue
        # Iterate over all artifacts from the run
        for artifact in json.loads(artifacts)['artifacts']:
          if artifact['name'] == artifact_name:
            # Artifact was found
            artifact_created_str = artifact["created_at"]
            print(f"[GithubFileHandler] Downloading Artifact {artifact_name} (Created at {artifact_created_str})... ", end="")
            # Get the download url
            status, headers, response = run._requester.requestJson("GET", artifact['archive_download_url'])
            if status != 302:
              print("[GithubFileHandler] Failed: Could not retrieve archive download URL: " + response)
              continue
            # Follow redirect.
            response = requests.get(headers['location'])
            if response.status_code != 200:
              print(f"[GithubFileHandler] Failed to download the file: {response.status_code} {response.reason}")
              continue
            # Read the compressed file contents
            compressed_artifact_content = io.BytesIO(response.content)
            # Decompress
            artifact_content = zipfile.ZipFile(compressed_artifact_content, "r")
            # Try to read the requested file
            try:
              file_content = artifact_content.read(file_name)
            except Exception as e:
              print("Failed.")
              print(f"[GithubFileHandler] Run '{run_name}', Artifact '{artifact_name}' does not contain file '{file_name}'. Valid files are:")
              for content_file_name in artifact_content.namelist():
                print(f" - {content_file_name}")
              raise FileHandlerError(f"Run '{run_name}', Artifact '{artifact_name}' does not contain file '{file_name}'.")
            # File download complete
            print("Complete.")
            return io.BytesIO(file_content), datetime.fromisoformat(artifact_created_str)
          else:
            found_artifacts.add(f"{run.raw_data['name']}/{artifact['name']}")
        if success:
          print("Success!")
    else:
      # Artifact was not found
      print(f"[GithubFileHandler] Error: Did not find Artifact '{artifact_name}' of run '{run_name}. Valid artifacts are:")
      for found_artifact in found_artifacts:
        print(f" - {found_artifact}")
      raise FileHandlerError(f"Did not find Artifact '{artifact_name}' of run '{run_name}'.")

  def close_connection(self):
    self.github.close()