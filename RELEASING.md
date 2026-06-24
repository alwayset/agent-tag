# Releasing Agent Tag

Agent Tag is published to PyPI as [`agent-tag`](https://pypi.org/project/agent-tag/).
Releases are cut from a GitHub Release and published automatically by
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) using PyPI
**trusted publishing** (OIDC — there is no stored API token).

## One-time prerequisite (human, once per project)

Before the first release can publish, a human with a PyPI account must register
the project and its trusted publisher. This cannot be automated because it
requires a logged-in PyPI session.

1. Sign in to <https://pypi.org> (create an account if needed).
2. Go to **Your account → Publishing** and add a **pending publisher** (this also
   reserves the project name on first publish, so the project does not need to
   exist yet):
   - **PyPI Project Name:** `agent-tag`
   - **Owner:** `alwayset`
   - **Repository name:** `agent-tag`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. (Recommended) In the GitHub repo, create an **Environment** named `pypi`
   (Settings → Environments) so you can add release protection rules / required
   reviewers if desired. The workflow references `environment: pypi`.

The `Owner`, `Repository`, `Workflow`, and `Environment` values must match the
workflow exactly, or PyPI will reject the OIDC token.

## Cutting a release

1. **Bump the version** in [`pyproject.toml`](pyproject.toml) (`[project].version`).
   Follow [SemVer](https://semver.org/): patch for fixes, minor for
   backward-compatible features, major for breaking changes.
2. **Update [`CHANGELOG.md`](CHANGELOG.md)** — move items out of `## [Unreleased]`
   into a new `## [X.Y.Z] — YYYY-MM-DD` section, and add the version's compare /
   tag link references at the bottom (mirroring the existing `0.1.0` entries).
3. **Commit** the bump on `main` (or via PR):

   ```sh
   git commit -am "release: vX.Y.Z"
   git push
   ```

   Confirm CI is green ([`ci.yml`](.github/workflows/ci.yml): ruff + pytest on
   3.11 / 3.12 / 3.13) before tagging.
4. **Tag and push:**

   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
5. **Create the GitHub Release** for tag `vX.Y.Z` (GitHub UI → Releases → Draft a
   new release, or `gh release create vX.Y.Z --title vX.Y.Z --notes "..."`). Use
   the CHANGELOG section as the release notes.
6. **Publishing the release** triggers `publish.yml`, which:
   - builds the sdist + wheel with `python -m build`, then
   - uploads to PyPI via `pypa/gh-action-pypi-publish` using trusted publishing
     (the `publish` job runs in the `pypi` environment with `id-token: write`).

   No token is configured anywhere — PyPI verifies the GitHub OIDC token against
   the trusted publisher registered above.

## Verifying

- Watch the **Publish to PyPI** workflow run under the repo's Actions tab.
- Confirm the new version appears at <https://pypi.org/project/agent-tag/>.
- Sanity-check an install in a clean environment:

  ```sh
  python3 -m venv /tmp/at && /tmp/at/bin/pip install agent-tag
  /tmp/at/bin/agent-tag --help
  ```

## Building locally (optional)

To reproduce the release artifacts without publishing:

```sh
python -m pip install build twine
python -m build              # writes sdist + wheel to dist/
python -m twine check dist/* # validates metadata
```

`dist/` is gitignored — do not commit build artifacts.
