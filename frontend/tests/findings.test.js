/**
 * The sentence under a check is composed, not written. These tests fix the
 * templates against the real answers for Flurstück 204 in Mölkau, and pin the
 * distinction the whole thing exists for: "not affected" and "no data here"
 * are different sentences, and only one of them is green.
 */
import { describe, it, expect } from "vitest";
import {
  noiseFinding, designationFinding, airQualityFinding, groundFinding,
  unavailableFinding, tallyFindings, tallyText, readBand, bandSpan,
  classifySoil, noiseInterpretation, WHO_LIMITS,
  GOOD, NOTE, OPEN
} from "../src/lib/findings.js";

describe("readBand / bandSpan", () => {
  it("reads a closed band", () => expect(readBand("Lden5559")).toEqual([55, 59]));
  it("reads an open top band", () => expect(readBand("LdenAb75")).toEqual([75, null]));
  it("reads a night band", () => expect(readBand("Lnight4549")).toEqual([45, 49]));
  it("spans several bands", () => expect(bandSpan(["Lden5054", "Lden5559"])).toEqual([50, 59]));
  it("keeps the top open when one band is open", () =>
    expect(bandSpan(["Lden7074", "LdenAb75"])).toEqual([70, null]));
  it("gives nothing for nothing", () => expect(bandSpan([])).toBeNull());
});

describe("noiseFinding", () => {
  it("reports the span across the parcel — the real answer for Mölkau 204", () => {
    const f = noiseFinding({
      day: { road: ["Lden5054", "Lden5559"], tram: [], air: [] },
      night: { road: ["Lnight4549"] },
      mappedNearby: true
    });
    expect(f.value).toBe("50–59 dB(A)");
    // The quieter half pulls the lower bound to 50, but part of the plot sits
    // in the 55-59 band -- that is the half worth knowing about.
    expect(f.status).toBe(NOTE);
    expect(f.text).toContain("Straßenverkehr, tags 50–59 dB(A).");
    expect(f.text).toContain("Nachts 45–49 dB(A).");
    expect(f.text).toContain("schneidet mehrere Bänder");
    expect(f.text).toContain("Straßenbahn und Fluglärm: nicht kartiert.");
    expect(f.interpretation.label).toBe("deutlich hörbar");
  });

  it("never calls a plot without a value quiet — mapped nearby or not", () => {
    // Naunhof, Bahnhofstraße: no band on the plot, 30 main-road polygons
    // within 2 km. That used to read "unter 45 dB(A)" in green.
    const nearby = noiseFinding({ day: {}, night: {}, mappedNearby: true });
    expect(nearby.status).toBe(NOTE);
    expect(nearby.value).toBe("keine Lärmdaten");
    expect(nearby.text).toContain("Hauptverkehrsstraßen");
    expect(nearby.text).toContain("nur vor Ort");
    expect(nearby.text).not.toMatch(/unter \d+ dB/);

    const unmapped = noiseFinding({ day: {}, night: {}, mappedNearby: false, radius: "2 km" });
    expect(unmapped.status).toBe(NOTE);
    expect(unmapped.value).toBe("keine Lärmdaten");
    expect(unmapped.text).toContain("Im Umkreis von 2 km ist nichts kartiert.");
  });

  it("flags a loud plot but not a quiet one", () => {
    expect(noiseFinding({ day: { road: ["Lden6569"] }, night: {}, mappedNearby: true }).status).toBe(NOTE);
    expect(noiseFinding({ day: { road: ["Lden5054", "Lden5559"] }, night: {}, mappedNearby: true }).status).toBe(NOTE);
    expect(noiseFinding({ day: { road: ["Lden4549"] }, night: {}, mappedNearby: true }).status).toBe(GOOD);
  });

  it("writes an open top band as 'ab'", () => {
    expect(noiseFinding({ day: { road: ["LdenAb75"] }, night: {}, mappedNearby: true }).value)
      .toBe("ab 75 dB(A)");
  });
});

describe("designationFinding", () => {
  it("reports a bracketed distance — the real answer for the Stünz LSG", () => {
    const f = designationFinding({
      hit: false, name: "Östliche Rietzschke – Stünz", subject: "Landschaftsschutzgebiet",
      distanceFrom: 350, distanceTo: 400, alsoNearby: 1
    });
    expect(f.status).toBe(GOOD);
    expect(f.value).toBe("350–400 m entfernt");
    expect(f.text).toContain("„Östliche Rietzschke – Stünz\", 350–400 m entfernt.");
    expect(f.text).toContain("Ein weiteres liegt innerhalb eines Kilometers.");
  });

  it("takes a short value where 'nicht betroffen' would read wrong", () => {
    const f = designationFinding({
      hit: false, subject: "Gebiet über 20 % Neigung", absentValue: "unter 20 %",
      absent: "Nicht in der Kulisse der Flächen über 20 % Neigung."
    });
    expect(f.value).toBe("unter 20 %");
  });

  it("says plainly when nothing is there", () => {
    const f = designationFinding({ hit: false, subject: "Wasserschutzgebiet" });
    expect(f.status).toBe(GOOD);
    expect(f.value).toBe("nicht betroffen");
    expect(f.text).toBe("Kein Wasserschutzgebiet am Grundstück.");
  });

  it("marks a hit as something to note", () => {
    const f = designationFinding({ hit: true, name: "Stadt Schneeberg", subject: "Radonvorsorgegebiet" });
    expect(f.status).toBe(NOTE);
    expect(f.text).toBe("Das Grundstück liegt im Radonvorsorgegebiet „Stadt Schneeberg\".");
  });
});

describe("airQualityFinding", () => {
  it("names the answering station and its distance", () => {
    const f = airQualityFinding({
      station: "Leipzig-Mitte", distanceKm: 4.6, hours: 48,
      values: { no2: 13.1, pm10: 11.8, pm25: 6.0, o3: 55.5 }
    });
    expect(f.status).toBe(GOOD);
    expect(f.value).toBe("NO₂ 13,1 µg/m³");
    expect(f.text).toContain("Station Leipzig-Mitte, 4,6 km entfernt");
    expect(f.text).toContain("Mittel aus 48 Stundenwerten");
  });

  it("stays open when no station answered", () => {
    expect(airQualityFinding({ station: null, values: {} }).status).toBe(OPEN);
  });
});

describe("classifySoil", () => {
  // The real BK50 wording for Flurstück 204 -- the sentence a buyer cannot use.
  const MOELKAU = "Hortisol ueber erodierter Parabraunerde aus gemischtem Schluff "
    + "ueber tiefem periglaziaerem Kies fuehrendem Lehm";

  it("reads the grain sizes out of the map's own German", () => {
    const s = classifySoil(MOELKAU, "LK_IV");
    expect(s.kind).toBe("gemischt");          // Schluff + Lehm, dazu Kies
    expect(s.grains).toEqual(expect.arrayContaining(["Lehm", "Schluff", "Kies"]));
    expect(s.air).toMatchObject({ label: "hoch", range: "13 – 26 Vol.-%" });
  });

  it("calls clay and loam cohesive and says what that costs", () => {
    const s = classifySoil("Pseudogley aus Lehm über Ton");
    expect(s.kind).toBe("bindig");
    expect(s.text).toContain("hält Wasser");
    expect(s.text).toContain("Rigole");
  });

  it("leaves the drainage question open when the air capacity contradicts the texture", () => {
    const s = classifySoil("Parabraunerde aus Lehm", "LK_V");
    expect(s.kind).toBe("bindig");
    expect(s.text).toContain("offen und muss geprüft werden");
    expect(s.text).not.toContain("Rigole");
  });

  it("calls sand and gravel coarse", () => {
    const s = classifySoil("Podsol aus Sand über Kies");
    expect(s.kind).toBe("rollig");
    expect(s.text).toContain("läuft rasch ab");
  });

  it("gives nothing when no grain size is named", () => {
    expect(classifySoil("Hortisol über erodierter Parabraunerde")).toBeNull();
  });
});

describe("groundFinding", () => {
  const MOELKAU = "Hortisol ueber erodierter Parabraunerde aus gemischtem Schluff "
    + "ueber tiefem periglaziaerem Kies fuehrendem Lehm";

  it("classifies the soil and keeps the drilling evidence beside it", () => {
    const f = groundFinding({
      soilText: MOELKAU, airCapacityClass: "LK_IV",
      boreholes: 14, radiusM: 300, nearestM: 82, nearestDepthM: 5,
      deepest: { depthM: 21, year: 2019 }
    });
    expect(f.value).toBe("gemischt");
    expect(f.text).toContain("Gemischter Boden");
    expect(f.text).toContain("Luftkapazität hoch");
    expect(f.text).toContain("14 Bohrungen im Umkreis von 300 m.");
    expect(f.text).toContain("Nächste 82 m entfernt, Endteufe 5,0 m.");
    expect(f.text).toContain("Tiefste in der Nähe 21 m (2019).");
    // The one sentence that must always be there.
    expect(f.text).toContain("ersetzt keine Baugrunduntersuchung");
    expect(f.detail).toBe(MOELKAU);
  });

  it("uses the singular for one borehole", () => {
    expect(groundFinding({ boreholes: 1, nearestM: 40 }).text).toContain("1 Bohrung im Umkreis");
  });

  it("stays open with nothing behind it", () => {
    expect(groundFinding({}).status).toBe(OPEN);
  });
});

describe("noiseInterpretation", () => {
  it("describes the plot by its louder end, not its quiet corner", () => {
    const i = noiseInterpretation([50, 59], [45, 49], "road");
    expect(i.label).toBe("deutlich hörbar");
    expect(i.everyday).toContain("hebt man beim Sprechen die Stimme");
    expect(i.notes[0]).toContain("Über dem Wert von 53 dB(A)");
    expect(i.notes.join(" ")).toContain("Nachts über der Empfehlung von 45 dB(A)");
  });

  it("says so plainly when the plot is below the recommendation", () => {
    const i = noiseInterpretation([45, 49], [40, 44], "road");
    expect(i.label).toBe("leise");
    expect(i.notes[0]).toContain("Unter dem Wert von 53 dB(A)");
    expect(i.notes.join(" ")).toContain("Nachts unter der Empfehlung");
  });

  it("names the cardiovascular threshold once it is reached", () => {
    const i = noiseInterpretation([65, 69], null, "road");
    expect(i.label).toBe("sehr laut");
    expect(i.notes.join(" ")).toContain("Ab 65 dB(A) steigt das Herz-Kreislauf-Risiko");
  });

  it("carries its source", () => {
    expect(noiseInterpretation([50, 54], null).source).toContain("UBA-Positionspapier 2019");
  });

  it("gives nothing without a measurement", () => {
    expect(noiseInterpretation(null, null)).toBeNull();
  });
});

describe("the tally that replaces a score", () => {
  it("counts the states and writes them out", () => {
    const findings = [
      { status: GOOD }, { status: GOOD }, { status: NOTE },
      { status: OPEN }, { status: OPEN }, { status: OPEN }
    ];
    const counts = tallyFindings(findings);
    expect(counts).toEqual({ good: 2, note: 1, open: 3 });
    expect(tallyText(counts)).toBe("2 ohne Befund · 1 zu beachten · 3 offen");
  });

  it("leaves out an empty state instead of writing a zero", () => {
    expect(tallyText(tallyFindings([{ status: GOOD }]))).toBe("1 ohne Befund");
  });

  it("names why an unavailable check is empty", () => {
    const f = unavailableFinding({ value: "keine Daten", text: "Für Sachsen liegt kein Dienst vor." });
    expect(f.status).toBe(OPEN);
    expect(f.text).toBe("Für Sachsen liegt kein Dienst vor.");
  });
});
