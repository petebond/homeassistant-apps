"""Puts the companion integration and blueprints into Home Assistant's config folder.

Why: the integration can't come through HACS from this repository (HACS wants one
integration at the root of a repository, and this one holds several apps). So the
app carries its own copy and installs it when it starts. After the first install,
or an update that changes it, Home Assistant needs a restart to load it; it then
finds the app by itself and offers to set the integration up.

Only Prepare's own folders are touched:
  /homeassistant/custom_components/prepare/
  /homeassistant/blueprints/automation/prepare/
"""
import filecmp
import logging
import shutil
from pathlib import Path

log = logging.getLogger("prepare.installer")

BUNDLED = Path(__file__).resolve().parent.parent  # /opt/prepare in the image
HA_CONFIG = Path("/homeassistant")


def _same_tree(a: Path, b: Path) -> bool:
    if not b.is_dir():
        return False
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__"])
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(_same_tree(a / d, b / d) for d in cmp.common_dirs)


def _copy(src: Path, dst: Path, what: str) -> bool:
    if not src.is_dir():
        log.warning("Bundled %s not found at %s - skipped", what, src)
        return False
    if _same_tree(src, dst):
        log.info("%s already up to date", what)
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    log.info("Installed %s to %s", what, dst)
    return True


def install(base: Path | None = None, ha_config: Path | None = None) -> bool:
    """Returns True if the integration changed (Home Assistant needs a restart)."""
    base = base or BUNDLED
    ha_config = ha_config or HA_CONFIG
    if not ha_config.is_dir():
        log.info("Home Assistant config folder not mounted - integration not installed")
        return False
    try:
        changed = _copy(base / "integration" / "custom_components" / "prepare",
                        ha_config / "custom_components" / "prepare", "Prepare integration")
        _copy(base / "blueprints" / "automation" / "prepare",
              ha_config / "blueprints" / "automation" / "prepare", "Prepare blueprints")
    except OSError as exc:
        log.warning("Could not install the integration or blueprints: %s", exc)
        return False
    if changed:
        log.warning("Prepare integration installed or updated - restart Home Assistant to load it.")
    return changed
