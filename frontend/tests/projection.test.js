/** WGS84 ⇄ metres, and proof that the basemap camera lands where the drawing draws. */
import { describe, it, expect } from "vitest";
import { toLocal, toWgs84, anchorOf, zoomFor, resolutionAt, cameraFor, projectWithCamera } from "../src/lib/projection.js";
import { fitScale, boundingBox } from "../src/lib/geometry.js";
import { realPlot } from "./helpers.js";

const LEIPZIG = { lat: 51.2829, lon: 12.4628 };

describe("WGS84 und Meter", () => {
  it("kommt hin und zurück", () => {
    const corners = [[12.4628, 51.2829], [12.4631, 51.2833], [12.4625, 51.2831]];
    const back = toWgs84(toLocal(corners, LEIPZIG), LEIPZIG);
    back.forEach(([lon, lat], i) => {
      expect(lon).toBeCloseTo(corners[i][0], 9);
      expect(lat).toBeCloseTo(corners[i][1], 9);
    });
  });

  it("misst einen bekannten Abstand", () => {
    // 0,001° Breite sind rund 111,3 m; 0,001° Länge auf 51°N rund 69,8 m.
    const [north] = toLocal([[LEIPZIG.lon, LEIPZIG.lat + 0.001]], LEIPZIG);
    const [east] = toLocal([[LEIPZIG.lon + 0.001, LEIPZIG.lat]], LEIPZIG);
    expect(north.y).toBeCloseTo(111.32, 1);
    expect(east.x).toBeCloseTo(69.8, 0);
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
  const drawing = (plot, width, height, margin) => {
    const box = boundingBox(plot.polygon);
    const scale = fitScale(plot.polygon, width, height, margin);
    const mx = (box.minX + box.maxX) / 2, my = (box.minY + box.maxY) / 2;
    return { scale, mx, my, px: x => width / 2 + (x - mx) * scale, py: y => height / 2 - (y - my) * scale };
  };

  // Both recorded parcels: one convex, one markedly concave.
  for (const plot of [realPlot("convex"), realPlot("concave")]) {
    for (const rotation of [0, 17, -46, 90]) {
      it(`${plot.id}, gedreht um ${rotation}° — Karte und Zeichnung decken sich`, () => {
        const width = 820, height = 620, margin = 40;
        const d = drawing(plot, width, height, margin);
        const camera = cameraFor({
          anchor: plot.anchor,
          centreMetres: { x: d.mx, y: d.my },
          metresPerPixel: 1 / d.scale,
          rotation
        });
        const centre = { x: width / 2, y: height / 2 };
        const R = (rotation * Math.PI) / 180;

        for (const v of plot.polygon) {
          const [lon, lat] = toWgs84([v], plot.anchor)[0];
          const onMap = projectWithCamera([lon, lat], camera, { width, height });
          // The SVG scene is rotated as a whole, so rotate the drawn point too.
          const dx = d.px(v.x) - centre.x, dy = d.py(v.y) - centre.y;
          const drawn = {
            x: centre.x + dx * Math.cos(R) - dy * Math.sin(R),
            y: centre.y + dx * Math.sin(R) + dy * Math.cos(R)
          };
          const distance = Math.hypot(onMap.x - drawn.x, onMap.y - drawn.y);
          expect(distance).toBeLessThan(1.5);   // unter anderthalb Bildpunkten
        }
      });
    }
  }

  it("dreht die Karte gegenläufig zur Zeichnung", () => {
    const camera = cameraFor({ anchor: LEIPZIG, centreMetres: { x: 0, y: 0 }, metresPerPixel: 0.2, rotation: 30 });
    expect(camera.bearing).toBe(-30);
  });
});
