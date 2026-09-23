/**
 * A new ground fades in over the old one instead of replacing it on the spot.
 *
 * jsdom has no WebGL, so the map here is a stand-in that only knows the three
 * things `MapStack` asks of one: `on`, `once`/`off` for "idle", and `remove`.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { FADE_MS, MapStack, TILE_FADE_MS, quickTiles } from "../src/lib/mapFade.js";

function fakeMap(element) {
  const listeners = {};
  return {
    element,
    removed: false,
    on(type, fn) { (listeners[type] ||= []).push(fn); },
    once(type, fn) {
      const wrapped = () => { this.off(type, wrapped); fn(); };
      wrapped.original = fn;
      this.on(type, wrapped);
    },
    off(type, fn) {
      listeners[type] = (listeners[type] || []).filter(l => l !== fn && l.original !== fn);
    },
    fire(type) { [...(listeners[type] || [])].forEach(fn => fn()); },
    remove() { this.removed = true; }
  };
}

describe("MapStack", () => {
  // jsdom runs no CSS transition, so the fade ends on the fallback timer.
  const FADE_OVER = FADE_MS + 250;
  let host;
  beforeEach(() => {
    vi.useFakeTimers();
    host = document.createElement("div");
    document.body.appendChild(host);
  });
  afterEach(() => {
    vi.useRealTimers();
    host.remove();
  });

  it("keeps a map invisible until it has drawn, then fades it in", () => {
    const stack = new MapStack();
    const ready = vi.fn();
    const map = stack.start(host, fakeMap, ready);
    expect(map.element.classList.contains("map-fade")).toBe(true);
    expect(map.element.classList.contains("is-shown")).toBe(false);

    map.fire("idle");
    expect(map.element.classList.contains("is-shown")).toBe(true);
    // Not ready half way through the fade: a picture then is a washed-out one.
    expect(ready).not.toHaveBeenCalled();
    vi.advanceTimersByTime(FADE_OVER);
    expect(ready).toHaveBeenCalledWith(map);
  });

  it("ends the fade on the element's own transitionend", () => {
    const stack = new MapStack();
    const ready = vi.fn();
    const map = stack.start(host, fakeMap, ready);
    map.fire("idle");
    map.element.dispatchEvent(new Event("transitionend"));
    expect(ready).toHaveBeenCalledWith(map);
  });

  it("leaves the old map in place until the new one is over it", () => {
    const stack = new MapStack();
    const old = stack.start(host, fakeMap);
    old.fire("idle");
    vi.advanceTimersByTime(FADE_OVER);

    stack.retire();
    const next = stack.start(host, fakeMap);
    expect(old.removed).toBe(false);
    expect(host.children).toHaveLength(2);
    // The new map lies on top.
    expect(host.lastElementChild).toBe(next.element);

    next.fire("idle");
    vi.advanceTimersByTime(FADE_OVER - 1);
    expect(old.removed).toBe(false);
    vi.advanceTimersByTime(1);
    expect(old.removed).toBe(true);
    expect([...host.children]).toEqual([next.element]);
  });

  it("shows a slow map early, over the old one, and drops the old one once complete", () => {
    // MapLibre never fires "idle" while tiles are outstanding -- a switch must
    // not wait for the slowest of them.
    const stack = new MapStack();
    const old = stack.start(host, fakeMap);
    old.fire("idle");
    vi.advanceTimersByTime(FADE_OVER);
    stack.retire();
    const next = stack.start(host, fakeMap);

    vi.advanceTimersByTime(400);
    expect(next.element.classList.contains("is-shown")).toBe(true);
    vi.advanceTimersByTime(FADE_OVER);
    // Still underneath: a tile the new map lacks shows the old ground, not paper.
    expect(old.removed).toBe(false);
    next.fire("idle");
    expect(old.removed).toBe(true);
  });

  it("drops the old map after a while even if the new one never completes", () => {
    const stack = new MapStack();
    const old = stack.start(host, fakeMap);
    stack.retire();
    stack.start(host, fakeMap);
    vi.advanceTimersByTime(400 + FADE_OVER + 4000);
    expect(old.removed).toBe(true);
  });

  it("does not let a superseded map clear the stack when its fade ends", () => {
    const stack = new MapStack();
    const first = stack.start(host, fakeMap);
    first.fire("idle");
    vi.advanceTimersByTime(FADE_OVER);

    stack.retire();
    const second = stack.start(host, fakeMap);
    second.fire("idle");            // its fade starts ...
    stack.retire();                 // ... and the user switches again
    const third = stack.start(host, fakeMap);
    vi.advanceTimersByTime(FADE_OVER);
    // Nothing is taken away while the third has not drawn yet.
    expect(first.removed).toBe(false);
    expect(second.removed).toBe(false);

    third.fire("idle");
    vi.advanceTimersByTime(FADE_OVER);
    expect(first.removed && second.removed).toBe(true);
    expect(third.removed).toBe(false);
  });

  it("takes every map away on clear", () => {
    const stack = new MapStack();
    const old = stack.start(host, fakeMap);
    stack.retire();
    const next = stack.start(host, fakeMap);
    stack.clear();
    expect(old.removed && next.removed).toBe(true);
    expect(host.children).toHaveLength(0);
  });
});

describe("quickTiles", () => {
  it("shortens the tile fade on raster layers and leaves the rest alone", () => {
    const style = quickTiles({
      version: 8,
      layers: [
        { id: "dop", type: "raster", source: "dop", paint: { "raster-opacity": 0.9 } },
        { id: "water", type: "fill", source: "osm" }
      ]
    });
    expect(style.layers[0].paint).toEqual({ "raster-opacity": 0.9, "raster-fade-duration": TILE_FADE_MS });
    expect(style.layers[1]).toEqual({ id: "water", type: "fill", source: "osm" });
  });
});
