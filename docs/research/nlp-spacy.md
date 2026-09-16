# Would a parser read a listing better than a regular expression?

**Research date: 2026-09-15.** Written in English: this is developer
documentation, only the user interface is German.

The question is narrow. `backend/app/search/indicia.py` reads German prose for
places, and it has one failure that keeps coming back: it looks for the word
that ties a place to the plot in the 60 characters *before* the name, so every
sentence that puts the trigger *after* the name is read as a bare mention and
never becomes an anchor. Two adverts in the corpus fail exactly there:

* „Thräna ist mit seinen etwa 765 Einwohnern ein kleiner Ortsteil der
  Kreisstadt Borna." — and Thräna is the answer.
* „Kitzen, ein idyllischer Ortsteil der Stadt Pegau, besticht durch …" — and
  Kitzen is the answer.

A language model reads both without effort, at a price per listing and behind
a citation gate. A dependency parser would do it deterministically, offline
and reviewably. So: measured, with `spaCy 3.8.16` and `de_core_news_md`, over
all ten adverts recorded at the time (`backend/tests/fixtures/inserate-sachsen.json`).

## 1. On a sentence, the parse is exactly what is needed

```
„Thräna ist … ein Ortsteil der Kreisstadt Borna."

  Thräna      PROPN  sb → ist          subject
  Ortsteil    NOUN   pd → ist          predicate
  Kreisstadt  NOUN   ag → Ortsteil     genitive attribute
  Borna       PROPN  nk → Kreisstadt
```

One `DependencyMatcher` rule walks subject → predicate → genitive → name and
produces (Thräna ⊂ Borna). Four rules cover every phrasing in the corpus:

| Rule | Covers |
|---|---|
| `teil_nach` | „im Ortsteil Plagwitz von Machern", „Ortsteil Lobstädt bei Neukieritzsch" |
| `teil_vor` | „Kitzen, ein idyllischer Ortsteil der Stadt Pegau" (apposition) |
| `teil_praedikativ` | „Thräna ist … ein Ortsteil der Kreisstadt Borna" |
| `entfernung` | „die ca. 6 km entfernte Kreisstadt Grimma" |

The last one is a bonus the regular expressions never offered: the distance
attaches to the adjective as a measure argument (`km ams→ entfernte`) and the
place hangs off the noun it modifies, so **distance and place come out as a
pair** regardless of word order — which is what the distance bands need.

## 2. On the real text, it falls apart

The same four rules over the adverts as they actually arrive:

```
 ✓ Großbothen ⊂ Grimma            correct
 ✓ ca. 6 km → Grimma              correct
 ~ Plagwitz ⊂ ?                   place yes, municipality no
 ✗ Lagebeschreibung ⊂ ?           the Thräna advert
 ✗ ca. 300 m → Leipzig            meant: Kitzen
 ✗ ca. 5 km → EDEKA               four times in a row
 ✗ fußläufig → Physiotherapien
```

The cause is not the model, it is the text. `# Lagebeschreibung` as a heading
without a full stop makes that word the subject of the sentence that follows,
and the distances sit in bullet lists:

```
- Bushaltestelle "Kitzen": ca. 300 m entfernt (Linie 120, Fahrzeit nach Leipzig: ca. 25 Minuten)
```

Without sentence structure the parser attaches to the nearest plausible noun,
and here that is Leipzig. **The two adverts the parser was fetched for are the
two with the bullet lists.**

## 3. Named entities are not the reason to take it

Over the ten adverts, `de_core_news_md` finds LOC/ORG entities that the
directory then filters. It is neither a superset nor a subset of what the
regular expressions find:

* **Finds what we miss:** Kitzen, Kreischau.
* **Misses what we have:** Thräna, Höfgen.
* **Does not repeat our false positives:** „Wiesen" is not a place to it.
* **Has its own:** „Glückwunsch!", „Wendehammers", „Doppelhaushälfte",
  „Ver – und Entsorgung notwendigen Medien", „www.GARANT-IMMO.de".

Harmless, because the district directory is the filter either way — but not
something to build on. Street names it does not help with at all: „Am Kurpark"
and „Platz des 21. September" are no more addresses to spaCy than to a suffix
pattern.

What it *does* supply and no pattern can: the **named points** a distance band
needs — „Cospudener See", „Kloster Nimbschen", „Hainer Seeufer", „Allee
Center", „EDEKA", „Leipzig-Südwest", „A38", „Haus Sonnenschein".

## 4. What it costs

| | |
|---|---|
| Disk | 126 MB spaCy + 60 MB `de_core_news_md` = **190 MB** in the image |
| Memory | **422 MB** RSS with the model loaded |
| Time | **68 ms** per advert (0,68 s for ten), `tok2vec, tagger, morphologizer, parser, lemmatizer, attribute_ruler, ner` |

## 5. Verdict

**Not yet — and the preparation is worth doing either way.**

What breaks the parser is a format problem, not a language problem. A listing
is half prose and half headings, bullets and key-value lines, and all three
readers suffer from it at once: the regular expression reads across block
boundaries, the parser turns a heading into a subject, and the model gets a
text with no structure. So the first step is **segmentation** — split the text
into headings, paragraphs, bullets and „Label: Wert" lines — which is small,
deterministic, and helps every channel. Afterwards a bullet like
„Bushaltestelle ‚Kitzen': ca. 300 m entfernt" is a key-value pair that needs
nobody who understands language.

Only then is the question worth asking again: how much of the relation problem
is left, and is it worth 190 MB. If it is, spaCy is the cheaper of the two
remaining answers — no per-listing cost, no citation gate, because a parse
cannot invent a statement the way a model can.

## 6. How to repeat this

```bash
backend/.venv/bin/pip install spacy
backend/.venv/bin/python -m spacy download de_core_news_md
```

The measurement scripts are not committed; they are twenty lines each — load
the corpus, run `nlp()` over `titel + beschreibung`, compare the LOC entities
against `gemarkungen-sachsen.json`, and run a `DependencyMatcher` with the
four rules above. Neither package is a dependency of this project.
