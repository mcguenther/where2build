/**
 * The search field takes an address, a parcel or a coordinate, and the field
 * has to decide which without asking. These cases pin the decision down —
 * especially the cheap one that saves the work: a German address never begins
 * with a digit, so once a digit leads, the address index is out.
 */
import { describe, it, expect } from "vitest";
import { classifyQuery, queryKindLabel } from "../src/lib/queryInput.js";

describe("classifyQuery", () => {
  it("reads nothing out of an empty field", () => {
    expect(classifyQuery("").kind).toBe("empty");
    expect(classifyQuery("   ").kind).toBe("empty");
  });

  describe("coordinates", () => {
    it("takes a decimal pair with a dot", () => {
      const r = classifyQuery("51.33652, 12.44176");
      expect(r.kind).toBe("coordinate");
      expect(r.certain).toBe(true);
      expect(r.coordinate).toMatchObject({ lat: 51.33652, lon: 12.44176, system: "wgs84" });
    });

    it("takes the German decimal comma, separator and all", () => {
      // The hard one: the comma is both the decimal mark and the separator.
      const r = classifyQuery("51,33652, 12,44176");
      expect(r.kind).toBe("coordinate");
      expect(r.coordinate.lat).toBeCloseTo(51.33652, 5);
      expect(r.coordinate.lon).toBeCloseTo(12.44176, 5);
    });

    it("takes a space-separated pair", () => {
      expect(classifyQuery("51.33652 12.44176").kind).toBe("coordinate");
    });

    it("strips degree signs and hemisphere letters", () => {
      const r = classifyQuery("N 51.33652° E 12.44176°");
      expect(r.kind).toBe("coordinate");
      expect(r.coordinate.lat).toBeCloseTo(51.33652, 5);
    });

    it("puts a reversed pair back in order, and says so", () => {
      const r = classifyQuery("12.44176, 51.33652");
      expect(r.kind).toBe("coordinate");
      expect(r.coordinate.lat).toBeCloseTo(51.33652, 5);
      expect(r.coordinate.swapped).toBe(true);
    });

    it("recognises UTM 33 easting and northing", () => {
      const r = classifyQuery("321804 5690356");
      expect(r.kind).toBe("coordinate");
      expect(r.coordinate).toMatchObject({ system: "utm33", easting: 321804, northing: 5690356 });
    });

    it("refuses a pair outside Germany rather than guessing", () => {
      expect(classifyQuery("40.7128, -74.0060").kind).not.toBe("coordinate");
    });
  });

  describe("parcels", () => {
    it("knows the 20-character AdV key on sight", () => {
      const r = classifyQuery("145592___00204____02");
      expect(r.kind).toBe("parcel");
      expect(r.certain).toBe(true);
      expect(r.parcelKey).toBe("145592___00204____02");
    });

    it("treats a denominator as proof: no address carries one", () => {
      const r = classifyQuery("Mölkau 85/1");
      expect(r.kind).toBe("parcel");
      expect(r.certain).toBe(true);
      expect(r.district).toBe("Mölkau");
      expect(r.parcelNumber).toEqual({ numerator: "85", denominator: "1" });
    });

    it("takes a letter denominator", () => {
      expect(classifyQuery("Moritzburg 41/e").parcelNumber).toEqual({ numerator: "41", denominator: "e" });
    });

    it("takes a district key in front of the number", () => {
      const r = classifyQuery("143044 85");
      expect(r.kind).toBe("parcel");
      expect(r.certain).toBe(true);
      expect(r.districtKey).toBe("143044");
    });

    it("says which half is missing when only a number was typed", () => {
      const r = classifyQuery("85/1");
      expect(r.kind).toBe("parcel");
      expect(r.certain).toBe(false);
      expect(r.missing).toBe("district");
      expect(r.search).toEqual([]);
    });
  });

  describe("addresses", () => {
    it("reads street and house number, and keeps the parcel reading open", () => {
      const r = classifyQuery("Lessingweg 44");
      expect(r.kind).toBe("ambiguous");
      expect(r.street).toBe("Lessingweg");
      expect(r.houseNumber).toBe("44");
      expect(r.search).toContain("address");
    });

    it("searches address and district while only letters are typed", () => {
      const r = classifyQuery("Lessingw");
      expect(r.search).toEqual(["address", "district"]);
    });
  });

  describe("the digit rule", () => {
    it("stops asking the address index once a digit leads", () => {
      // Neither a coordinate nor a parcel number -- and no German address
      // starts with a digit, so there is nothing to look up.
      const r = classifyQuery("9999999 8888888 7777777");
      expect(r.search).not.toContain("address");
    });

    it("never asks the address index for a coordinate", () => {
      expect(classifyQuery("51.33652, 12.44176").search).toEqual(["coordinate"]);
    });

    it("never asks the address index for a parcel key", () => {
      expect(classifyQuery("145592___00204____02").search).toEqual(["parcel"]);
    });
  });

  describe("queryKindLabel", () => {
    it("names each reading in German", () => {
      expect(queryKindLabel(classifyQuery("51.33652, 12.44176"))).toBe("Koordinate");
      expect(queryKindLabel(classifyQuery("321804 5690356"))).toBe("Koordinate (UTM 33)");
      expect(queryKindLabel(classifyQuery("Mölkau 85/1"))).toBe("Flurstück");
      expect(queryKindLabel(classifyQuery("85/1"))).toBe("Flurstück — Gemarkung fehlt");
      expect(queryKindLabel(classifyQuery("Lessingweg 44"))).toBe("Adresse oder Flurstück");
    });
  });
});
