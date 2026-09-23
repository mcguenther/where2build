/**
 * A new ground fades in over the old one instead of replacing it on the spot.
 *
 * jsdom has no WebGL, so the map here is a stand-in that only knows the three
 * things `MapStack` asks of one: `on`, `once`/`off` for "idle", and `remove`.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { FADE_MS, MapStack } from "../src/lib/mapFade.js";

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
    vi.advanceTimersByTime(FADE_MS);
    expect(ready).toHaveBeenCalledWith(map);
  });

  it("leaves the old map in place until the new one is over it", () => {
    const stack = new MapStack();
    const old = stack.start(host, fakeMap);
    old.fire("idle");
    vi.advanceTimersByTime(FADE_MS);

    stack.retire();
    const next = stack.start(host, fakeMap);
    expect(old.removed).toBe(false);
    expect(host.children).toHaveLength(2);
    // The new map lies on top.
    expect(host.lastElementChild).toBe(next.element);

    next.fire("idle");
    vi.advanceTimersByTime(FADE_MS - 1);
    expect(old.removed).toBe(false);
    vi.advanceTimersByTime(1);
    expect(old.removed).toBe(true);
    expect([...host.children]).toEqual([next.element]);
  });

  it("does not let a superseded map clear the stack when its fade ends", () => {
    const stack = new MapStack();
    const first = stack.start(host, fakeMap);
    first.fire("idle");
    vi.advanceTimersByTime(FADE_MS);

    stack.retire();
    const second = stack.start(host, fakeMap);
    second.fire("idle");            // its fade starts ...
    stack.retire();                 // ... and the user switches again
    const third = stack.start(host, fakeMap);
    vi.advanceTimersByTime(FADE_MS);
    // Nothing is taken away while the third has not drawn yet.
    expect(first.removed).toBe(false);
    expect(second.removed).toBe(false);

    third.fire("idle");
    vi.advanceTimersByTime(FADE_MS);
    expect(first.removed && second.removed).toBe(true);
    expect(third.removed).toBe(false);
  });

  it("shows a map whose tiles never all arrive, after a while", () => {
    // MapLibre never fires "idle" while one tile keeps failing.
    const stack = new MapStack();
    const map = stack.start(host, fakeMap);
    vi.advanceTimersByTime(2500);
    expect(map.element.classList.contains("is-shown")).toBe(true);
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
