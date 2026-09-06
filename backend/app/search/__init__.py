"""Resolving a listing to the parcel it is actually selling.

The search is a staircase, not a pipeline: it stops at the first step that can
answer, and every later step exists only for the listings the earlier ones
cannot settle. The happy case -- a cadastral district and a parcel number in
the text or on an attached map extract -- costs two requests and no model call.

What decides and what merely orders is kept strictly apart:

* **Hard filters decide.** Only official facts: a parcel number resolved
  against ALKIS, the cadastral district, and ``ave:flaeche`` when the listing's
  figure is exact.
* **Soft scoring orders.** Everything inferential -- a rounded area, a street,
  the land use, a broker's distance claim.

That split is what lets the weights ship uncalibrated: they can produce an
unhelpful ordering, never a wrong answer.
"""

from .engine import SearchEngine, run_search
from .indicia import collect_indicia
from .ladder import tolerance_ladder

__all__ = ["SearchEngine", "run_search", "collect_indicia", "tolerance_ladder"]
