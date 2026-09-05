"""Reading a listing's images for cadastral references.

A seller who attaches a Geoportal print has already answered the question the
whole search exists for. Tesseract reads that print's title block reliably --
"Flurstück 790/11", "Wiesenstraße - Großbothen" -- and reads nothing at all off
a site photograph, which is exactly the property that makes this safe: the
pattern filter carries the safety, so every image is read and no classifier is
needed.

The ladder is measured, not guessed (``docs/research/flurstueck-identifikation.md``
§ 10). Upscaling is the fix, not orientation detection:

    upscale to a long edge of 1500 px  ->  --psm 6  ->  --psm 1 only if nothing matched

A 2x Lanczos upscale repaired ``--psm 1``'s blindness to a 180 deg flip and a
7 deg tilt with no deskewing at all. An orientation pre-pass costs the same on
*every* image and brings three failure modes with it, including reporting the
complement for a quarter turn -- so there is none.

The dangerous failure is not an empty answer. At 7 deg and native size the
reader returned ``Flurstück 790717``: it found the word and corrupted the
digits, and a plausible wrong number resolves to a real but foreign parcel.
That is why nothing here trusts its own output -- the numbers go out as
*Indizien* to be checked against the cadastre, and one whose numerator is wider
than the AdV key allows is dropped before it costs a request.

Tesseract is an optional dependency, like the POI index: absent, this module
says so and the search runs on text alone.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
from dataclasses import dataclass, field

from ..errors import UpstreamError
from ..schemas import Indiz
from ..settings import AppSettings
from ..upstream import request
from ..search.indicia import normalise_parcel_number, parcel_label

SERVICE_NAME = "Die Texterkennung"

# The binary and the German language data. Both have to be there: the default
# model reads German text as English words and the parcel numbers survive, but
# the words around them -- "Flurstück", "Gemarkung" -- are what the patterns
# key on.
BINARY = "tesseract"
LANGUAGE = "deu"

# Long edge to scale every image up to before reading. The research treated
# this as a rescue for small prints and assumed real photographs would exceed
# it -- measured 05.09.2026, they do not: what a portal *serves* is 678 x 960
# for the cadastral extract and 960 x 720 for a site photograph, whatever the
# camera produced. So the upscale that repaired a 7 degree tilt and a 180
# degree flip runs on every image in production, not on the odd one.
TARGET_LONG_EDGE = 1500

# Two passes, in this order. ``psm 6`` reads an upright block; ``psm 1``
# handles the quarter turns and costs another ~900 ms, so it only runs when
# the first pass matched nothing.
PAGE_MODES = ("6", "1")

# How long one image may take. Measured sequentially: 0,9 s when the first
# pass matches, up to ~5 s for a large photograph where both passes run and
# find nothing. Generous against that, and short enough that one stuck process
# cannot hold up a search.
TIMEOUT_S = 30

# „Flurstück 790/11“, „Flurstücks-Nr. 85/1“, „Flst. 476“. The label has to be
# there: a bare number on a map is one of the small in-map labels, which the
# same measurement showed come out as garbage.
_PARCEL_RE = re.compile(
    r"(?:flurst(?:ü|u|ue)?ck(?:s)?[\s\-]*(?:nr\.?|nummer)?|flst\.?[\s\-]*(?:nr\.?)?)"
    r"\s*[:.]?\s*(\d{1,6})\s*(?:/\s*(\d{1,5}|[a-zA-Z]))?",
    re.IGNORECASE,
)
_DISTRICT_RE = re.compile(
    r"gemarkung\s*[:.]?\s*([A-ZÄÖÜ][\wäöüßÄÖÜ.\-]{2,}(?:[ -][A-ZÄÖÜ][\wäöüßÄÖÜ.\-]+)?)",
    re.IGNORECASE,
)

# The GeoSN signs every sheet it issues with its own address. A street or a
# place read next to one of these is the authority, not the plot.
_AUTHORITY = ("landesamt", "geobasisinformation", "olbrichtplatz", "geosn", "staatsbetrieb")

# How much text an image has to yield before it is worth looking at. Below
# this the reader found noise, and noise is where a garbled number comes from.
MIN_CHARACTERS = 12


def available() -> bool:
    """Whether this server can read an image at all."""

    return shutil.which(BINARY) is not None


def languages() -> list[str]:
    if not available():
        return []
    try:
        result = subprocess.run(
            [BINARY, "--list-langs"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in result.stdout.splitlines()[1:] if line.strip()]


def status() -> dict[str, object]:
    """What ``/api/health`` says about this channel."""

    langs = languages()
    return {
        "konfiguriert": available() and LANGUAGE in langs,
        "sprachen": langs,
        "pfad": shutil.which(BINARY),
    }


def upscale(data: bytes, target: int = TARGET_LONG_EDGE) -> bytes:
    """Enlarge to a long edge of ``target``, Lanczos, never shrink.

    This one step is what the measurements say to spend effort on: it repaired
    a 7 degree tilt without any deskewing and a 180 degree flip that ``--psm 1``
    could not otherwise see. Pillow is an optional dependency; without it the
    image goes to the reader as it came, which is what the "native size" column
    of the measurement table describes.
    """

    try:
        from PIL import Image
    except ImportError:
        return data
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            longest = max(image.size)
            if longest >= target:
                return data
            factor = target / longest
            size = (round(image.width * factor), round(image.height * factor))
            enlarged = image.convert("RGB").resize(size, Image.LANCZOS)
            buffer = io.BytesIO()
            enlarged.save(buffer, format="PNG")
            return buffer.getvalue()
    except Exception:
        # A file Pillow cannot open is one Tesseract will reject too, and it
        # will say so more usefully than a stack trace here.
        return data


def read(data: bytes, page_mode: str = PAGE_MODES[0]) -> tuple[str, str | None]:
    """One Tesseract pass over one image: the text, and why there is none.

    The second half of the pair is what stops a failure from reading as an
    answer. Tesseract exits 0 with an empty page for a photograph of a lawn --
    which is the correct answer -- and it also produces nothing when it is
    killed, and those two must not look alike.
    """

    try:
        result = subprocess.run(
            [BINARY, "stdin", "stdout", "-l", LANGUAGE, "--psm", page_mode],
            input=data,
            capture_output=True,
            timeout=TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise UpstreamError(
            f"{SERVICE_NAME} ist auf diesem Server nicht installiert."
        ) from exc
    except subprocess.TimeoutExpired:
        return "", f"nach {TIMEOUT_S} s abgebrochen"
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        return "", (detail[-1] if detail else f"Rückgabewert {result.returncode}")
    return result.stdout.decode("utf-8", "replace"), None


def _line_around(text: str, position: int) -> str:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    return text[start : end if end >= 0 else len(text)]


def _mentions_authority(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _AUTHORITY)


@dataclass
class ImageReading:
    """What one image yielded, and what it cost.

    ``failed`` is the point of this class rather than a bare string: a reader
    that timed out and a picture of a lawn produce the same empty answer, and
    reporting the first as the second is how "no cadastral extract attached"
    becomes a claim the search never actually checked.
    """

    quelle: str
    text: str = ""
    modes: list[str] = field(default_factory=list)
    parcels: list[str] = field(default_factory=list)
    districts: list[str] = field(default_factory=list)
    failed: str | None = None

    @property
    def useful(self) -> bool:
        return bool(self.parcels or self.districts)


def patterns(text: str) -> tuple[list[str], list[str]]:
    """Parcel numbers and cadastral districts, as far as the text is trustworthy.

    A number whose numerator is wider than the AdV parcel key allows is not a
    parcel number but a misread one, and it is dropped here rather than sent to
    the cadastre, where it would resolve to a real but foreign parcel.
    """

    parcels: list[str] = []
    for match in _PARCEL_RE.finditer(text):
        raw = f"{match.group(1)}/{match.group(2)}" if match.group(2) else match.group(1)
        parsed = normalise_parcel_number(raw)
        if parsed:
            label = parcel_label(*parsed)
            if label not in parcels:
                parcels.append(label)

    districts: list[str] = []
    for match in _DISTRICT_RE.finditer(text):
        name = match.group(1).strip(" .:-")
        # Bounded by the line. The authority signs on its own line, and a
        # character window instead reaches into the caption above it and
        # suppresses the district the sheet is actually about.
        line = _line_around(text, match.start())
        if name not in districts and not _mentions_authority(line):
            districts.append(name)
    return parcels, districts


def read_image(data: bytes, quelle: str = "Bild") -> ImageReading:
    """The full ladder over one image: upscale, ``psm 6``, then ``psm 1``."""

    reading = ImageReading(quelle=quelle)
    if not available():
        reading.failed = "keine Texterkennung auf diesem Server"
        return reading
    enlarged = upscale(data)
    for mode in PAGE_MODES:
        text, failure = read(enlarged, mode)
        reading.modes.append(mode)
        if failure:
            reading.failed = failure
            return reading
        if len(text.strip()) < MIN_CHARACTERS:
            continue
        parcels, districts = patterns(text)
        if parcels or districts:
            reading.text = text
            reading.parcels, reading.districts = parcels, districts
            return reading
        reading.text = reading.text or text
    return reading


async def fetch(url: str, app_settings: AppSettings) -> bytes:
    """One listing image, through the same client as every other upstream."""

    response = await request(
        "GET",
        url,
        service=SERVICE_NAME,
        advice="Bitte das Bild herunterladen und von Hand prüfen.",
        timeout_s=app_settings.http_timeout_s,
        user_agent=app_settings.user_agent,
    )
    return response.content


def as_indicia(readings: list[ImageReading], start: int = 0) -> list[Indiz]:
    """Turn what was read into Indizien the search can weigh.

    ``bild`` is the second-most trusted source there is -- an official extract
    outranks everything but a person -- and that is precisely why nothing here
    is allowed to be a verdict: the search cross-checks the parcel it resolves
    against the listing's own area and municipality before it may agree.
    """

    out: list[Indiz] = []
    count = start
    for reading in readings:
        for number in reading.parcels:
            count += 1
            out.append(
                Indiz(
                    id=f"ocr{count}",
                    art="flurstueck",
                    wert=number,
                    text=f"Flurstück {number} auf einem Bild der Anzeige",
                    beleg=_excerpt(reading.text, number),
                    quelle="bild",
                    sicherheit=0.95,
                )
            )
        for district in reading.districts:
            count += 1
            out.append(
                Indiz(
                    id=f"ocr{count}",
                    art="gemarkung",
                    wert=district,
                    text=f"Gemarkung {district} auf einem Bild der Anzeige",
                    beleg=_excerpt(reading.text, district),
                    quelle="bild",
                    sicherheit=0.95,
                    beziehung="liegt_in",
                )
            )
    return out


def _excerpt(text: str, needle: str, pad: int = 40) -> str:
    """The line the value was read from -- the Beleg a person can check.

    Text recognition has no rectangle to hand back here, so the line it read is
    the closest thing to one. An Indiz whose evidence cannot be looked at is an
    Indiz nobody can resolve a contradiction with.
    """

    lowered, target = text.lower(), needle.split("/")[0].lower()
    index = lowered.find(target)
    if index < 0:
        return "aus einem Bild gelesen"
    left = max(0, index - pad)
    return " ".join(text[left : index + len(needle) + pad].split())
