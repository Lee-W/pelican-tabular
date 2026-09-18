# Coordinated tabular / OSM release

Both repositories bump versions and create tags automatically after a push to
`main`. A version tag then triggers their PyPI publishing workflow. Treat merging
either feature branch as the start of a release.

1. Merge tabular first, retaining the feature commit's `feat:` classification.
   Keep the development version at 0.5.0; Commitizen should create 0.6.0, its
   changelog entry and tag. Wait for the PyPI workflow to finish successfully.
2. Prepare OSM while it is still on its feature branch. Remove the temporary
   `pelican-tabular` entry in `[tool.uv.sources]`, then run `uv lock`. Confirm the
   lock selects the published tabular release from the registry, without a
   sibling path. Update OSM's development instructions to match.
3. Run OSM's `uv sync --locked --no-sources`, `uv run poe ci`, and its browser
   integration job against the released tabular code. Commit the registry lock
   and configuration changes before merging OSM.
4. Merge OSM and wait for its automatic version bump, tag and PyPI publication.
   The release guard `uv sync --locked --no-sources --no-dev` must pass. Never
   merge the temporary local-source lock into a release expecting that check
   to be bypassed.
5. Upgrade the blogs after both packages are published, regenerate their
   lockfiles and build each site. Ordinary pages retain their existing
   shortcodes and assets. Adopt a database view separately by defining
   `TABULAR_VIEWS` and adding an explicit `view` shortcode.

The OSM feature branch's temporary sibling lock was created with tabular 0.6.0
development metadata. The tabular feature branch now retains 0.5.0 for the
automatic bump, so a normal OSM dependency sync against that checkout is an
intermediate mismatch. Resolve it through step 2 after publication; do not
lower OSM's minimum dependency to the released 0.5.0, which lacks the shared API.

Branch commits do not publish anything. Pushing or merging these branches and
performing the release steps are separate from the initial local commits.
