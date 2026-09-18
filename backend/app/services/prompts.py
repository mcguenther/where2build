"""What the model is told, and what it is deliberately not told.

The prompts live here rather than in the router because they are the one part
of the model channel that is *content*: what a reader has to know about German
property adverts and about this search to produce something the Beleg gate will
accept. They are German, because the text they are about is German and because
a mixed-language instruction is one more thing for a model to resolve.

Four decisions shape them.

**A system prompt and a user message, not one blob.** The instructions are the
same on every listing and the listing is not, so they belong in the stable half
— which is also the half both APIs cache. Sent as one string, every listing
re-sent the whole instruction as fresh tokens.

**The listing is fenced, and the fence is announced.** An advert is prose with
headings, colons and its own „Hinweis:" lines, and it arrives after a hint of
ours; without a delimiter the boundary between our sentences and the seller's
is a matter of interpretation. The fence is a line of percent signs because no
German advert has one, and it grows a character at a time until the text
provably does not contain it — the delimiter is derived from the text, never
assumed about it.

**The vocabulary is ours, so it is stated.** `Ortsebene` and `Ortsbeziehung`
are enumerated in the schema, and a name in an enum conveys nothing: the schema
says „liegt_in" is allowed and not that „die ca. 6 km entfernte Kreisstadt
Grimma" is the opposite of it. The same goes for the shape of the answer. Both
wire formats carry the JSON schema — `response_format` there, `output_config`
here — but a strict schema only rejects a wrong shape; it does not say that an
absent value is null rather than an omission, that `wortlaut` keeps the
rounding, or that a denominator can be a letter. `RÜCKGABE` demands JSON and
nothing else, and `SHAPE` states the rest as a commented skeleton — not a
worked example, which offers values to copy from a listing that is not the
one being read. Every distinction below is one this project measured and got
wrong first.

**The model never learns what our own readers concluded.** This is the one rule
worth stating twice. Handing it our findings would make it agree with us, and
the divergence log in `services.lehrbuch` would then measure nothing at all: a
teacher shown the student's answers is not a teacher. Reference *material* is a
different thing and is welcome — the list of cadastral districts that actually
exist is data about Saxony, not an answer about this advert.
"""

from __future__ import annotations

from ..schemas import BEFUND_VORLAGE

# How many known district names travel with a listing. Enough for every
# candidate an advert's prose can plausibly raise, short enough that the list
# cannot become the bulk of the request.
MAX_DISTRICT_HINTS = 40

# The delimiter around the listing. Percent signs because a German advert has
# prices with „%" in them but never a run of four, and `fence_for` proves that
# for the text at hand rather than trusting it.
FENCE = "%%%%"


def fence_for(text: str) -> str:
    """A delimiter the listing provably does not contain.

    A fence that occurs inside the advert would let the text end early, which
    is the one failure mode a delimiter is supposed to remove. Growing it by
    one character terminates: a text of *n* characters cannot contain a fence
    of *n* + 1.
    """

    fence = FENCE
    while fence in text:
        fence += "%"
    return fence


# The answer's shape, as a commented skeleton rather than a filled example.
# A worked example is read as material: the first draft of this section carried
# a real Befund and the risk it brings -- values to copy, a listing that is not
# the one being read. The skeleton cannot be copied from, and each line can say
# the one thing the JSON schema cannot: what the field means, and when it is
# null. The comments are stripped in `test_prompts`, which then parses what is
# left and holds its key set against `InseratBefund` -- so a field added to the
# schema, or invented here, fails a test rather than travelling unexplained.
SHAPE = """\
{
  // Immer genau diese Zeichenkette.
  "vorlage": "%(vorlage)s",

  "felder": {
    // Straße und Hausnummer; ein Ortsname allein ist keine Adresse.
    "adresse": {"wert": "Text | null", "beleg": "Textstelle | null"},

    // Gesamtpreis in Euro. Ein Preis je Quadratmeter ist keiner: dann null.
    // wert: Zahl ohne Einheit und Tausenderpunkt (69000). wortlaut: „69.000 €".
    "kaufpreis_eur": {"wert": "Zahl | null", "wortlaut": "Text | null", "beleg": "Textstelle | null"},

    // Die Fläche des Grundstücks, siehe oben. wortlaut behält das „ca.".
    "grundstuecksflaeche_m2": {"wert": "Zahl | null", "wortlaut": "Text | null", "beleg": "Textstelle | null"}
  },

  // Ein Eintrag je Aussage — derselbe Name mehrfach, wenn der Text
  // Verschiedenes über ihn sagt. Sonst leer.
  "orte": [
    {
      "name": "Text",
      "ebene": "gemarkung | ortsteil | gemeinde | strasse | unbekannt",
      "beziehung": "liegt_in | liegt_an | entfernt_von | erwaehnt",
      // Nur, wenn der Text Kilometer nennt; Minuten sind keine.
      "entfernung_km": "Zahl | null",
      "beleg": "Textstelle | null"
    }
  ],

  // Nur ausdrücklich genannte, nie aus einer Adresse abgeleitete. Sonst leer.
  "flurstuecke": [
    {
      "gemarkung": "Text | null",
      "flur": "Text | null",
      // Zähler Zahl, Nenner Zeichenkette — er kann ein Buchstabe sein (41/e).
      "zaehler": "Zahl",
      "nenner": "Text | null",
      "beleg": "Textstelle | null"
    }
  ],

  // Aus der Liste oben, sonst leer.
  "vorbehalte": ["teilflaeche | mehrere-grundstuecke | ausserhalb-sachsens"]
}\
""" % {"vorlage": BEFUND_VORLAGE}


_INSTRUCTIONS = """\
Du liest Immobilieninserate für Grundstücke in Sachsen und gibst wieder, was \
darin steht. Du bist der letzte von mehreren Lesern; vor dir haben Mustererkenner \
denselben Text gelesen. Deine Aufgabe ist nicht, ihnen zuzustimmen, sondern den \
Text unabhängig zu lesen.

DAS INSERAT

Der Inseratstext steht in der Nachricht zwischen zwei Zeilen, die nur aus \
Prozentzeichen bestehen. Alles vor der ersten dieser Zeilen ist ein Hinweis von \
uns und gehört nicht zum Inserat. Die Begrenzungszeilen selbst sind kein Text \
des Inserats und dürfen in keinem Beleg vorkommen.

Zu jedem Wert gehört ein Beleg: eine zusammenhängende Textstelle aus dem Inserat, \
in der der Wert wörtlich steht. Der Beleg wird Zeichen für Zeichen gegen den Text \
geprüft — nur Leerraum, Anführungszeichen und Groß-/Kleinschreibung werden dabei \
vereinheitlicht. Umformuliert, zusammengefasst oder aus zwei Sätzen zusammengesetzt \
besteht er die Prüfung nicht, und der Wert wird dann verworfen. Lieber null als ein \
Wert ohne belastbaren Beleg.

Rechne nichts aus. Ein Kaufpreis, der sich aus Fläche mal Preis je Quadratmeter \
ergibt, steht nicht im Inserat. Runde nicht und rechne keine Einheiten um, wenn die \
Zahl dadurch anders im Text stünde.

Namen, Telefonnummern, Mail-Adressen und andere Kontaktdaten werden nicht erfasst.

ORTE: ihre Ebene und ihre Beziehung zum Grundstück

Das ist der Teil, für den du gebraucht wirst — Fläche und Preis liest ein \
Mustererkenner besser. Deutsche Inserate nennen mehrere Orte auf verschiedenen \
Ebenen in einem Satz, und welche Ebene gemeint ist, entscheidet die Suche.

ebene:
  gemarkung  — der Katasterbezirk; oft gleichlautend mit einem Ortsteil
  ortsteil   — ein Ortsteil, dessen Katasterzugehörigkeit offenbleibt
  gemeinde   — die Gemeinde oder Stadt, also die Ebene darüber
  strasse    — eine Straße
  unbekannt  — nicht entscheidbar

beziehung:
  liegt_in     — das Grundstück liegt dort
  liegt_an     — es grenzt daran
  entfernt_von — der Ort wird als entfernt beschrieben; das spricht GEGEN ihn \
als Lage des Grundstücks
  erwaehnt     — der Ort kommt vor, ohne dass der Satz das Grundstück dorthin setzt

Gemessene Fälle, an denen einfache Regeln gescheitert sind:

„Baugrundstück in Großbothen, einem OT von Grimma" — zwei Orte, zwei Ebenen:
  Großbothen ebene=gemarkung beziehung=liegt_in
  Grimma     ebene=gemeinde  beziehung=liegt_in

„Thräna ist mit seinen etwa 765 Einwohnern ein kleiner Ortsteil der Kreisstadt \
Borna." — die Beziehung steht HINTER dem Namen, nicht davor:
  Thräna ebene=gemarkung beziehung=liegt_in
  Borna  ebene=gemeinde  beziehung=liegt_in

„Über die B107 erreichen Sie die ca. 6 km entfernte Kreisstadt Grimma."
  Grimma ebene=gemeinde beziehung=entfernt_von entfernung_km=6
  Derselbe Ortsname kann in einem Inserat beides sein; entscheidend ist der Satz.

„Gute Anbindung an Leipzig" / „in der Nähe von Leipzig" — eine Aussage über die \
Verkehrslage, nicht über den Ort des Grundstücks:
  Leipzig beziehung=erwaehnt

„Weiterführende Schulen in Roitzsch sind in 15 Minuten erreichbar." — sagt, wo die \
Schulen sind, nicht wo das Grundstück ist:
  Roitzsch beziehung=erwaehnt

„Kitzen, ein idyllischer Ortsteil der Stadt Pegau" — zwischen Artikel und \
Gattungswort steht im Deutschen fast immer ein Adjektiv; die Beziehung gilt trotzdem.

Das Grundstück liegt in genau einem Ort. Nennt das Inserat mehrere, die einander \
widersprechen, gib beide mit ihrem jeweiligen Beleg an — die Suche zeigt den \
Widerspruch, sie löst ihn nicht still auf.

FLURSTÜCKE

Ein Grundstück besteht oft aus mehreren Flurstücken. Mehrere Nummern in einem Satz \
(„Flurstück 790/11 sowie 238/3") sind dieses eine Grundstück, keine Alternativen — \
gib alle an. Der Nenner kann ein Buchstabe sein (41/e). Erfinde keine Nummer und \
leite keine aus einer Adresse ab.

FLÄCHE UND PREIS

Ein Inserat nennt mehrere Flächen. Gemeint ist die des Grundstücks — nicht die \
bebaubare Fläche, nicht die Grundfläche, nicht die Wohnfläche, und nicht die Spanne \
anderer Grundstücke im selben Baugebiet („Grundstücke zwischen 360 und 800 m²"). \
Schreibe in `wortlaut`, wie die Zahl dasteht, mit „ca." wenn es dort steht: gerundet \
und exakt werden von der Suche verschieden behandelt.

VORBEHALTE

Trage in `vorbehalte` ein, was die Zahlen relativiert, wenn es im Text steht:
  teilflaeche          — eine noch zu vermessende Teilfläche eines größeren Flurstücks
  mehrere-grundstuecke — das Inserat bewirbt mehrere Grundstücke zugleich
  ausserhalb-sachsens  — das Grundstück liegt nicht in Sachsen\
"""


_RETURN = """\
RÜCKGABE

Antworte ausschließlich mit einem JSON-Objekt genau dieser Struktur: kein Satz \
davor, keiner danach, keine Code-Zäune, keine zusätzlichen Felder. Jedes Feld \
wird gesetzt — was das Inserat nicht hergibt, bekommt null, Listen bleiben leer. \
Lass nichts weg und erfinde nichts, um ein Feld zu füllen.

Die Kommentarzeilen erklären die Felder und gehören nicht in deine Antwort.

%(shape)s\
""" % {"shape": SHAPE}


SYSTEM = f"{_INSTRUCTIONS}\n\n{_RETURN}"


def user_message(text: str, districts: list[str] | None = None) -> str:
    """The listing, fenced, and the reference material that goes with it.

    ``districts`` are names from the Saxon cadastral district register that
    occur in this text. They are *material*, not an answer: which of them the
    advert means, and on which level, is what the model is being asked. A name
    that is not in the register is worth knowing about too, so the list is
    offered rather than imposed.

    Nothing our own readers concluded goes in here. Handing the model our
    findings would make it agree with us, and the divergence log would then
    measure nothing — a teacher shown the student's answers is not a teacher.
    """

    parts = []
    if districts:
        named = ", ".join(sorted(set(districts))[:MAX_DISTRICT_HINTS])
        parts.append(
            "Diese Namen aus dem Text stehen im sächsischen Gemarkungsverzeichnis: "
            f"{named}.\nDas sagt nur, dass es sie gibt — ob und wie das Inserat sie "
            "meint, steht im Text. Namen, die nicht in der Liste stehen, sind "
            "trotzdem anzugeben, wenn der Text sie als Ort nennt."
        )
    fence = fence_for(text)
    parts.append("Das Inserat steht zwischen den Zeilen aus Prozentzeichen.")
    parts.append(f"{fence}\n{text}\n{fence}")
    return "\n\n".join(parts)


# The web-fetch call is a different job: bring the page back, do not read it.
# It gets no vocabulary and no examples, because anything it is told about
# fields is an invitation to summarise instead of quote.
FETCH = (
    "Es geht um ein Grundstücksinserat in Sachsen. Gib den Anzeigentext "
    "vollständig und unverändert wieder — Überschrift, Beschreibung, "
    "Angabenliste, Lagebeschreibung. Fasse nicht zusammen, lasse nichts weg "
    "und erfinde nichts."
)


__all__ = [
    "FENCE",
    "FETCH",
    "MAX_DISTRICT_HINTS",
    "SHAPE",
    "SYSTEM",
    "fence_for",
    "user_message",
]
