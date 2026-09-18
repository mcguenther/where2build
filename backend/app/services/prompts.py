"""What the model is told, and what it is deliberately not told.

The prompts live here rather than in the router because they are the one part
of the model channel that is *content*: what a reader has to know about German
property adverts and about this search to produce something the Beleg gate will
accept. They are German, because the text they are about is German and because
a mixed-language instruction is one more thing for a model to resolve.

Three decisions shape them.

**A system prompt and a user message, not one blob.** The instructions are the
same on every listing and the listing is not, so they belong in the stable half
— which is also the half both APIs cache. Sent as one string, every listing
re-sent the whole instruction as fresh tokens.

**The vocabulary is ours, so it is stated.** `Ortsebene` and `Ortsbeziehung`
are enumerated in the schema, and a name in an enum conveys nothing: the schema
says „liegt_in" is allowed and not that „die ca. 6 km entfernte Kreisstadt
Grimma" is the opposite of it. Every distinction below is one this project
measured and got wrong first — they are the same traps the patterns in
`search.indicia` carry, written as examples instead of as regular expressions.

**The model never learns what our own readers concluded.** This is the one rule
worth stating twice. Handing it our findings would make it agree with us, and
the divergence log in `services.lehrbuch` would then measure nothing at all: a
teacher shown the student's answers is not a teacher. Reference *material* is a
different thing and is welcome — the list of cadastral districts that actually
exist is data about Saxony, not an answer about this advert.
"""

from __future__ import annotations

# How many known district names travel with a listing. Enough for every
# candidate an advert's prose can plausibly raise, short enough that the list
# cannot become the bulk of the request.
MAX_DISTRICT_HINTS = 40


SYSTEM = """\
Du liest Immobilieninserate für Grundstücke in Sachsen und gibst wieder, was \
darin steht. Du bist der letzte von mehreren Lesern; vor dir haben Mustererkenner \
denselben Text gelesen. Deine Aufgabe ist nicht, ihnen zuzustimmen, sondern den \
Text unabhängig zu lesen.

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


def user_message(text: str, districts: list[str] | None = None) -> str:
    """The listing, and the reference material that goes with it.

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
    parts.append(f"Inserat:\n\n{text}")
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


__all__ = ["FETCH", "MAX_DISTRICT_HINTS", "SYSTEM", "user_message"]
