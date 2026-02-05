"""
Credits to mkdocs-yamp-plugin for the inspiration
"""

from __future__ import annotations

import os
import shutil
import fnmatch
import logging
import tempfile
import sh
from contextlib import contextmanager
from pathlib import Path
from mkdocs.plugins import BasePlugin
from mkdocs.config.base import Config
from mkdocs.config import config_options as c
from mkdocs.exceptions import PluginError
from mkdocs.structure.pages import Page

from typing import TYPE_CHECKING, Callable, Literal
from collections.abc import Generator

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.livereload import LiveReloadServer

log = logging.getLogger("mkdocs.plugins." + __name__)


@contextmanager
def set_directory(path: Path) -> Generator[None, None, None]:
    """Sets the cwd within the context

    Args:
        path (Path): The path to the cwd

    Yields:
        None
    """

    origin = Path().absolute()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)


class RepoItem(Config):  # type: ignore
    """represents a repository defined by the user"""

    # the repository URL to clone
    # or the path to copy
    url = c.Type(str)

    # the branch of the repository to clone
    branch = c.Type(str, default="master")

    # a list of globs specifying paths within
    # the repository to clone
    include = c.ListOfItems(c.Type(str), default=[])

    def do_validation(self) -> None:
        """validates the user configuration"""
        if not self.url:
            raise PluginError("repo does not define a url or a path")

        if Path(self.url).is_dir() and self.branch:
            log.info(f"{self.url} is a path, ignoring branch option {self.branch}")


class DiracXDocsConfig(Config):  # type: ignore
    """defines the plugin configuration"""

    # the list of repositories to clone
    repos = c.ListOfItems(c.SubConfig(RepoItem), default=[])


class DiracxDoc(BasePlugin[DiracXDocsConfig]):  # type: ignore
    """Aggregates repositories defined by users in the mkdocs.yaml"""

    _temp_dir = ""

    # Original diracx location
    _original_dir: Path = Path().absolute()

    # Track file sources for edit URL generation: path -> (repo_url, branch)
    _file_sources: dict[str, tuple[str, str]] = {}

    def __init__(self) -> None:
        self._temp_dir = tempfile.mkdtemp()

    def on_startup(
        self, *, command: Literal["build", "gh-deploy", "serve"], dirty: bool
    ) -> None:
        """
        registers this plugin instance to persist across builds during mkdocs serve
        """
        ...

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig | None:
        for repo in self.config.repos:
            try:
                repo.do_validation()
            except:
                log.warning("misconfigured repo: %s", repo)
                raise

        config["docs_dir"] = Path(self._temp_dir) / "docs"
        config["config_file_path"] = Path(self._temp_dir) / "mkdocs.yml"

        # Some extensions obviously rely on the basepath, so modify it
        config["mdx_configs"].setdefault('pymdownx.snippets',{})['base_path'] = Path(self._temp_dir)
        return config

    def _record_doc_files(self, docs_dir: Path, repo_url: str, branch: str) -> None:
        """Record the source repository for all markdown files in a docs directory.

        Args:
            docs_dir: Path to the docs directory to scan
            repo_url: The repository URL or local path
            branch: The branch name
        """
        if not docs_dir.is_dir():
            return
        for md_file in docs_dir.rglob("*.md"):
            # Get path relative to docs directory
            rel_path = md_file.relative_to(docs_dir)
            self._file_sources[str(rel_path)] = (repo_url, branch)

    def on_pre_build(self, *, config: MkDocsConfig) -> None:
        """Merge all the doc together"""
        # Reset file sources tracking for each build
        self._file_sources = {}

        # Copy the current directory (which should be the diracx repo)
        shutil.copytree(
            self._original_dir,
            self._temp_dir,
            dirs_exist_ok=True,
            ignore=lambda x, y: [fn for fn in y if fnmatch.fnmatch(fn, ".*")],
        )

        # Record diracx files using the repo_url from config
        diracx_repo_url = config.get("repo_url", "")
        self._record_doc_files(
            self._original_dir / "docs", diracx_repo_url, "main"
        )

        with set_directory(Path(self._temp_dir)):
            sh.git.init(".")
            for repo in self.config.repos:
                repo_path = Path(repo.url)
                if repo_path.is_dir():
                    for repo_dir in repo.include:
                        log.info(f"Copying path {repo_path / Path(repo_dir)}")
                        shutil.copytree(
                            repo_path / Path(repo_dir),
                            self._temp_dir / Path(repo_dir),
                            dirs_exist_ok=True,
                        )
                    # Record files from local path
                    self._record_doc_files(repo_path / "docs", repo.url, repo.branch)
                else:
                    repo_hash = str(abs(hash(repo.url)))
                    log.info(f"Cloning {repo}")
                    if repo_hash not in sh.git.remote():
                        sh.git.remote.add(repo_hash, repo.url)
                    sh.git.fetch(repo_hash)
                    # Get list of doc files from the remote branch before checkout
                    # so we know exactly which files come from this repo
                    for repo_dir in repo.include:
                        if repo_dir == "docs" or repo_dir.startswith("docs/"):
                            try:
                                tree_output = sh.git(
                                    "ls-tree",
                                    "-r",
                                    "--name-only",
                                    f"{repo_hash}/{repo.branch}",
                                    repo_dir,
                                )
                                for file_path in str(tree_output).strip().split("\n"):
                                    if file_path.endswith(".md"):
                                        # Path is like "docs/admin/foo.md", we want "admin/foo.md"
                                        rel_path = file_path.removeprefix("docs/")
                                        self._file_sources[rel_path] = (
                                            repo.url,
                                            repo.branch,
                                        )
                            except sh.ErrorReturnCode:
                                # Directory might not exist in this repo
                                pass
                    sh.git.checkout(f"{repo_hash}/{repo.branch}", "--", *repo.include)

    def on_shutdown(self) -> None:
        """Remove the temporary directory
        Do NOT clean on on_post_build to be able to
        reuse the content if it is a remote repository
        """
        if self._temp_dir:
            shutil.rmtree(self._temp_dir)

    def on_serve(
        self, server: LiveReloadServer, /, *, config: MkDocsConfig, builder: Callable  # type: ignore
    ) -> LiveReloadServer | None:
        # Do not watch the temporary directory
        # but the actual sources if they are local
        watched_paths = list(server._watched_paths)
        for path in watched_paths:
            server.unwatch(path)
        server.watch(str(self._original_dir / "docs"))
        server.watch(str(self._original_dir / "mkdocs.yml"))
        for repo in self.config.repos:
            repo_path = Path(repo.url)
            if repo_path.is_dir():
                server.watch(str(repo_path / "docs"))
        return server

    def on_page_context(
        self,
        context: dict,
        page: Page,
        config: MkDocsConfig,
        **kwargs,
    ) -> dict | None:
        """Modify page.edit_url to point to the correct source repository."""
        src_path = page.file.src_path
        if src_path in self._file_sources:
            repo_url, branch = self._file_sources[src_path]
            # Skip if local path (development mode)
            if not Path(repo_url).is_dir():
                repo_url = repo_url.rstrip("/").removesuffix(".git")
                page.edit_url = f"{repo_url}/edit/{branch}/docs/{src_path}"
        return context
