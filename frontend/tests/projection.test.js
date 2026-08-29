/** WGS84 ⇄ metres, and proof that the basemap camera lands where the drawing draws. */
import { describe, it, expect } from "vitest";
import { toLocal, toWgs84, anchorOf, zoomFor, resolutionAt, cameraFor, projectWithCamera } from "../src/lib/projection.js";
import { fitScale, boundingBox } from "../src/lib/geometry.js";
import { echtesGrundstueck } from "./hilfe.js";

const LEIPZIG = { lat: 51.2829, lon: 12.4628 };

describe("WGS84 und Meter", () => {
  it("kommt hin und zurück", () => {
    const ecken = [[12.4628, 51.2829], [12.4631, 51.2833], [12.4625, 51.2831]];
    const zurueck = toWgs84(toLocal(ecken, LEIPZIG), LEIPZIG);
    zurueck.forEach(([lon, lat], i) => {
      expect(lon).toBeCloseTo(ecken[i][0], 9);
      expect(lat).toBeCloseTo(ecken[i][1], 9);
    });
  });

  it("misst einen bekannten Abstand", () => {
    // 0,001° Breite sind rund 111,3 m; 0,001° Länge auf 51°N rund 69,8 m.
    const [nord] = toLocal([[LEIPZIG.lon, LEIPZIG.lat + 0.001]], LEIPZIG);
    const [ost] = toLocal([[LEIPZIG.lon + 0.001, LEIPZIG.lat]], LEIPZIG);
    expect(nord.y).toBeCloseTo(111.32, 1);
    expect(ost.x).toBeCloseTo(69.8, 0);
  });

  it("legt den Anker in die Mitte der Punkte", () => {
    expect(anchorOf([[10, 50], [12, 52]])).toEqual({ lon: 11, lat: 51 });
  });

  it("Zoom und Auflösung sind zueinander invers", () => {
    for (const zoom of [14, 17, 19.5]) {
      expect(zoomFor(LEIPZIG.lat, resolutionAt(LEIPZIG.lat, zoom))).toBeCloseTo(zoom, 9);
    }
  });
});

describe("Kamera unter der Zeichnung", () => {
  /* The drawing's own projection, copied from SitePlan: metres → viewBox units. */
  const zeichnung = (plot, breite, hoehe, rand) => {
    const box = boundingBox(plot.polygon);
    const scale = fitScale(plot.polygon, breite, hoehe, rand);
    const mx = (box.minX + box.maxX) / 2, my = (box.minY + box.maxY) / 2;
    return { scale, mx, my, px: x => breite / 2 + (x - mx) * scale, py: y => hoehe / 2 - (y - my) * scale };
  };

  // Both recorded parcels: one convex, one markedly concave.
  for (const plot of [echtesGrundstueck("konvex"), echtesGrundstueck("konkav")]) {
    for (const drehung of [0, 17, -46, 90]) {
      it(`${plot.id}, gedreht um ${drehung}° — Karte und Zeichnung decken sich`, () => {
        const breite = 820, hoehe = 620, rand = 40;
        const z = zeichnung(plot, breite, hoehe, rand);
        const kamera = cameraFor({
          anchor: plot.anker,
          centreMetres: { x: z.mx, y: z.my },
          metresPerPixel: 1 / z.scale,
          rotation: drehung
        });
        const mitte = { x: breite / 2, y: hoehe / 2 };
        const R = (drehung * Math.PI) / 180;

        for (const v of plot.polygon) {
          const [lon, lat] = toWgs84([v], plot.anker)[0];
          const aufKarte = projectWithCamera([lon, lat], kamera, { width: breite, height: hoehe });
          // The SVG scene is rotated as a whole, so rotate the drawn point too.
          const dx = z.px(v.x) - mitte.x, dy = z.py(v.y) - mitte.y;
          const gezeichnet = {
            x: mitte.x + dx * Math.cos(R) - dy * Math.sin(R),
            y: mitte.y + dx * Math.sin(R) + dy * Math.cos(R)
          };
          const abstand = Math.hypot(aufKarte.x - gezeichnet.x, aufKarte.y - gezeichnet.y);
          expect(abstand).toBeLessThan(1.5);   // unter anderthalb Bildpunkten
        }
      });
    }
  }

  it("dreht die Karte gegenläufig zur Zeichnung", () => {
    const k = cameraFor({ anchor: LEIPZIG, centreMetres: { x: 0, y: 0 }, metresPerPixel: 0.2, rotation: 30 });
    expect(k.bearing).toBe(-30);
  });
});
