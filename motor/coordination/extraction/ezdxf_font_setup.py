"""Register a default TrueType font for ezdxf in headless/Docker environments."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("dupla.coordination.ezdxf_fonts")

_FONT_DIRS: tuple[Path, ...] = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/liberation2"),
)

_BOOTSTRAPPED = False


def ensure_ezdxf_fallback_fonts() -> None:
    """Point ezdxf at system DejaVu/Liberation fonts; rebuild cache if needed."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    from ezdxf import options
    from ezdxf.fonts import fonts

    if fonts.font_manager.has_font("DejaVuSans.ttf"):
        return

    support_dirs = list(options.support_dirs)
    added = False
    for directory in _FONT_DIRS:
        if not directory.is_dir():
            continue
        text = str(directory)
        if text not in support_dirs:
            support_dirs.append(text)
            added = True
    if not added:
        return

    options.support_dirs = support_dirs
    try:
        fonts.build_system_font_cache()
    except Exception:
        logger.debug("ezdxf font cache rebuild failed", exc_info=True)
        return

    if fonts.font_manager.has_font("DejaVuSans.ttf"):
        logger.info("ezdxf default font ready: DejaVuSans.ttf")
    else:
        logger.warning("ezdxf font dirs configured but DejaVuSans.ttf still missing")


if __name__ == "__main__":
    ensure_ezdxf_fallback_fonts()
    from ezdxf.fonts import fonts as _fonts

    assert _fonts.font_manager.has_font("DejaVuSans.ttf"), "DejaVuSans.ttf not registered"
    print("ezdxf_font_setup ok")
