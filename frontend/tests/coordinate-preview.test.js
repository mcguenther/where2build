/**
 * The map preview under a typed coordinate, against two recorded ALKIS answers:
 * Flurstück 204 and its neighbour 205 in Mölkau (Lessingweg 44 and 46). The
 * points asked for are taken from those same outlines, so every number the
 * component shows comes out of a real answer.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import moelkau204 from "./fixtures/parcel-moelkau.json";
import moelkau205 from "./fixtures/parcel-moelkau-205.json";
import moelkauBoth from "./fixtures/parcel-moelkau-zwei.json";
import { toScreen, fromScreen } from "../src/lib/routes.js";

vi.mock("../src/lib/api.js", () => ({
  PAGE_LIMIT: 3000000,
  resolveParcel: vi.fn()
}));
const { resolveParcel } = await import("../src/lib/api.js");
const { default: CoordinatePreview, PREVIEW_HEIGHT, LOOKUP_DELAY_MS } =
  await import("../src/components/CoordinatePreview.vue");

/** Mean of a recorded outline's vertices — inside both of these convex plots. */
const inside = collection => {
  const ring = collection.features[0].geometry.coordinates[0].slice(0, -1);
  return {
    lat: ring.reduce((s, c) => s + c[1], 0) / ring.length,
    lon: ring.reduce((s, c) => s + c[0], 0) / ring.length
  };
};
const at204 = inside(moelkau204);
const at205 = inside(moelkau205);

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};

const open = (point = at204) => mount(CoordinatePreview, { props: { lat: point.lat, lon: point.lon } });

/** jsdom lays nothing out; give the map the box its own frame describes. */
const layOut = w => {
  const svg = w.find("svg").element;
  const { width, height } = w.vm.frame;
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width, height, right: width, bottom: height, x: 0, y: 0 });
  return svg;
};

/* jsdom has no PointerEvent, and test-utils cannot put a clientX on the
   MouseEvent it falls back to — so the event is built by hand. */
const pointer = (type, { x, y }) => {
  const event = new MouseEvent(type, { clientX: x, clientY: y, button: 0, bubbles: true, cancelable: true });
  Object.defineProperty(event, "pointerId", { value: 1 });
  return event;
};

const press = async (w, point) => {
  const pixel = toScreen([point.lon, point.lat], w.vm.fit);
  const svg = w.find("svg").element;
  svg.dispatchEvent(pointer("pointerdown", pixel));
  svg.dispatchEvent(pointer("pointerup", pixel));
  await w.vm.$nextTick();
  return pixel;
};

beforeEach(() => {
  resolveParcel.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("Kartenvorschau unter einer Koordinate", () => {
  it("zeigt beim Nachschlagen nur den Punkt und sagt, dass gesucht wird", () => {
    resolveParcel.mockReturnValue(new Promise(() => {}));
    const w = open();
    expect(resolveParcel).toHaveBeenCalledWith({ lat: at204.lat, lon: at204.lon });
    expect(w.text()).toContain("Flurstück wird nachgeschlagen …");
    expect(w.find(".kartenvorschau__punkt").exists()).toBe(true);
    expect(w.find(".kartenvorschau__flurstueck").exists()).toBe(false);
  });

  it("nennt das Flurstück unter dem Punkt mit der amtlichen Fläche und umrandet es", async () => {
    resolveParcel.mockResolvedValue(moelkau204);
    const w = open();
    await flushPromises();
    expect(w.find(".kv-status").text()).toBe("Punkt liegt in Mölkau 204");
    expect(w.find(".kv-status b").text()).toBe("Mölkau 204");
    // 650 m² is the recorded `flaeche_amtlich_m2`, not the 645,57 of the polygon.
    expect(w.text()).toContain("650 m²");
    expect(w.text()).not.toContain("645");
    expect(w.findAll(".kartenvorschau__flurstueck path").length).toBe(2);
    expect(w.emitted("parcel").at(-1)).toEqual([moelkau204]);
  });

  it("nennt mehrere Flurstücke als Grenze und keine zusammengezählte Fläche", async () => {
    // The point in 204 with both parcels returned: only 204 contains it.
    resolveParcel.mockResolvedValue(moelkauBoth);
    const inOne = open();
    await flushPromises();
    expect(inOne.find(".kv-status").text()).toBe("Punkt liegt in Mölkau 204");

    // The register falls back to whatever its one-metre box touched; a point
    // in neither outline must not read as lying inside one of them.
    const w = open({ lat: at205.lat + 0.0005, lon: at205.lon });
    await flushPromises();
    expect(w.find(".kv-status").text()).toBe("Punkt liegt an der Grenze von Mölkau 204 und 205");
    expect(w.findAll(".kartenvorschau__flurstueck path").length).toBe(4);
    expect(w.text()).not.toContain("1.299 m²");
  });

  it("zeigt die deutsche Meldung des Backends, wenn der Dienst ausfällt", async () => {
    const message = "Das Liegenschaftskataster (ALKIS) antwortet gerade nicht.";
    resolveParcel.mockRejectedValue(Object.assign(new Error(message), { status: 502 }));
    const w = open();
    await flushPromises();
    expect(w.find(".kv-status").text()).toBe(message);
    expect(w.find(".kartenvorschau__flurstueck").exists()).toBe(false);
    expect(w.emitted("parcel").at(-1)).toEqual([null]);
  });

  it("sagt schlicht, wenn an dem Punkt kein Flurstück liegt", async () => {
    resolveParcel.mockRejectedValue(Object.assign(new Error("Zu dieser Angabe wurde kein Flurstück gefunden."), { status: 404 }));
    const w = open();
    await flushPromises();
    expect(w.find(".kv-status").text()).toBe("An diesem Punkt wurde kein Flurstück gefunden.");
    expect(w.text()).not.toContain("m²");
  });

  it("verschiebt den Punkt per Klick im Verschiebemodus und schlägt neu nach", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    resolveParcel.mockResolvedValueOnce(moelkau204).mockResolvedValueOnce(moelkau205);
    const w = open();
    await flushPromises();
    layOut(w);

    // Outside the mode a press on the map does nothing.
    await press(w, at205);
    expect(w.emitted("move")).toBeUndefined();

    const button = w.find("button.kv-verschieben");
    expect(button.text()).toBe("Punkt verschieben");
    expect(button.attributes("aria-pressed")).toBe("false");
    await button.trigger("click");
    expect(button.attributes("aria-pressed")).toBe("true");
    expect(w.find("svg").attributes("tabindex")).toBe("0");

    const pixel = await press(w, at205);
    const [lon, lat] = fromScreen(pixel, w.vm.fit);
    expect(w.emitted("move")).toEqual([[{ lat, lon }]]);
    expect(Math.abs(lat - at205.lat)).toBeLessThan(1e-9);
    expect(Math.abs(lon - at205.lon)).toBeLessThan(1e-9);
    // The old parcel is gone at once; the cadastre is asked after the pause.
    expect(w.find(".kv-status").text()).toBe("Flurstück wird nachgeschlagen …");
    expect(w.find(".kartenvorschau__flurstueck").exists()).toBe(false);
    expect(w.emitted("parcel").at(-1)).toEqual([null]);
    expect(resolveParcel).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(LOOKUP_DELAY_MS);
    await flushPromises();
    expect(resolveParcel).toHaveBeenCalledTimes(2);
    expect(resolveParcel).toHaveBeenLastCalledWith({ lat, lon });
    expect(w.find(".kv-status").text()).toBe("Punkt liegt in Mölkau 205");
    expect(w.text()).toContain("649 m²");

    // The parent echoing the move back is not a new place to look up.
    await w.setProps({ lat, lon });
    await flushPromises();
    expect(resolveParcel).toHaveBeenCalledTimes(2);
  });

  it("fasst mehrere Pfeiltasten zu einer Abfrage zusammen", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    resolveParcel.mockResolvedValue(moelkau204);
    const w = open();
    await flushPromises();
    await w.find("button.kv-verschieben").trigger("click");
    const svg = w.find("svg");
    await svg.trigger("keydown", { key: "ArrowUp" });
    await svg.trigger("keydown", { key: "ArrowUp" });
    await svg.trigger("keydown", { key: "ArrowRight" });
    expect(w.emitted("move")).toHaveLength(3);
    const last = w.emitted("move").at(-1)[0];
    expect(last.lat).toBeGreaterThan(at204.lat);
    expect(last.lon).toBeGreaterThan(at204.lon);
    await vi.advanceTimersByTimeAsync(LOOKUP_DELAY_MS);
    expect(resolveParcel).toHaveBeenCalledTimes(2);

    await svg.trigger("keydown", { key: "Escape" });
    expect(w.find("button.kv-verschieben").attributes("aria-pressed")).toBe("false");
  });

  it("verwirft eine Antwort, die von einem älteren Punkt stammt", async () => {
    const slow = deferred();
    resolveParcel.mockReturnValueOnce(slow.promise).mockResolvedValueOnce(moelkau205);
    const w = open(at204);
    await w.setProps({ lat: at205.lat, lon: at205.lon });
    await flushPromises();
    expect(w.find(".kv-status").text()).toBe("Punkt liegt in Mölkau 205");

    slow.resolve(moelkau204);
    await flushPromises();
    expect(w.find(".kv-status").text()).toBe("Punkt liegt in Mölkau 205");
    expect(w.emitted("parcel").map(([p]) => p)).not.toContain(moelkau204);
  });

  it("behält in jedem Zustand dieselbe Höhe", async () => {
    const heightOf = w => w.find(".kartenvorschau").attributes("style");
    const expected = `height: ${PREVIEW_HEIGHT}px;`;
    expect(PREVIEW_HEIGHT).toBe(170);

    const slow = deferred();
    resolveParcel.mockReturnValueOnce(slow.promise);
    const w = open();
    expect(heightOf(w)).toBe(expected);
    slow.resolve(moelkau204);
    await flushPromises();
    expect(w.find(".kv-status").text()).toContain("Mölkau 204");
    expect(heightOf(w)).toBe(expected);

    resolveParcel.mockRejectedValueOnce(Object.assign(new Error("Das Backend ist nicht erreichbar. Läuft der Server?"), { status: 0 }));
    await w.setProps({ lat: at205.lat, lon: at205.lon });
    await flushPromises();
    expect(w.find(".kv-status").text()).toContain("nicht erreichbar");
    expect(heightOf(w)).toBe(expected);
    // The frame the drawing is laid out in follows the same constant.
    expect(w.find("svg").attributes("viewBox").split(" ")[3]).toBe(String(PREVIEW_HEIGHT - 2));
  });

  it("zeichnet die Karte aus den Kacheln des eigenen Proxys und beschriftet sie", async () => {
    resolveParcel.mockResolvedValue(moelkau204);
    const w = open();
    await flushPromises();
    const tiles = w.findAll(".kartenvorschau__grund image");
    expect(tiles.length).toBeGreaterThan(0);
    for (const tile of tiles) expect(tile.attributes("href")).toMatch(/^\/api\/tiles\/webatlas\/18\/\d+\/\d+\.png$/);
    expect(w.find("svg").attributes("aria-label")).toMatch(/^Kartenausschnitt um den Punkt 51,3365\d° N · 12,4418\d° O$/);
    expect(w.text()).toContain("© GeoSN");
  });
});
