import { describe, expect, it } from "vitest";
import { placeAccountMenu } from "./placeAccountMenu";

const pad = 8;
const gap = 8;

function menuEdges(
  placed: ReturnType<typeof placeAccountMenu>,
  viewportHeight: number,
  contentHeight: number,
) {
  const height = Math.min(contentHeight, placed.maxHeight);
  const bottom = viewportHeight - placed.bottom;
  return { top: bottom - height, bottom, left: placed.left, right: placed.left + placed.width };
}

describe("placeAccountMenu", () => {
  it("opens above the entire footer, not the account trigger", () => {
    const viewport = { width: 1440, height: 900 };
    const footer = { top: 812, right: 280, bottom: 890, left: 0 };
    const trigger = { top: 848, right: 268, bottom: 884, left: 12 };
    const placed = placeAccountMenu({ viewport, footer, trigger });

    expect(placed.bottom).toBe(viewport.height - footer.top + gap);
    expect(placed.bottom).not.toBe(viewport.height - trigger.top + gap);

    const box = menuEdges(placed, viewport.height, 240);
    expect(box.bottom).toBeLessThanOrEqual(footer.top - gap);
    expect(box.bottom).toBeLessThanOrEqual(trigger.top);
  });

  it("uses the account trigger as the horizontal anchor", () => {
    const placed = placeAccountMenu({
      viewport: { width: 1440, height: 900 },
      footer: { top: 812, right: 280, bottom: 890, left: 0 },
      trigger: { top: 848, right: 268, bottom: 884, left: 12 },
    });
    expect(placed.left).toBe(12);
    expect(placed.width).toBe(220);
  });

  it("clamps to the viewport instead of overflowing the right edge", () => {
    const viewport = { width: 390, height: 844 };
    const placed = placeAccountMenu({
      viewport,
      footer: { top: 740, right: 378, bottom: 832, left: 12 },
      trigger: { top: 786, right: 370, bottom: 822, left: 200 },
    });
    expect(placed.left).toBeGreaterThanOrEqual(pad);
    expect(placed.left + placed.width).toBeLessThanOrEqual(viewport.width - pad);
    expect(placed.width).toBeLessThanOrEqual(viewport.width - pad * 2);
  });

  it("shrinks with maxHeight before overlapping the runtime-status row", () => {
    const viewport = { width: 1024, height: 768 };
    const footer = { top: 96, right: 280, bottom: 176, left: 0 };
    const trigger = { top: 132, right: 268, bottom: 168, left: 12 };
    const placed = placeAccountMenu({ viewport, footer, trigger });
    const naturalHeight = 240;

    expect(placed.maxHeight).toBe(footer.top - gap - pad);
    expect(placed.maxHeight).toBeLessThan(naturalHeight);

    const box = menuEdges(placed, viewport.height, naturalHeight);
    expect(box.bottom).toBeLessThanOrEqual(footer.top - gap);
    expect(box.top).toBeGreaterThanOrEqual(pad);
  });

  it("stays above a collapsed 64px footer rail", () => {
    const viewport = { width: 1440, height: 900 };
    const footer = { top: 836, right: 64, bottom: 900, left: 0 };
    const trigger = { top: 848, right: 50, bottom: 884, left: 14 };
    const placed = placeAccountMenu({ viewport, footer, trigger });
    const box = menuEdges(placed, viewport.height, 240);

    expect(placed.left).toBe(14);
    expect(box.bottom).toBeLessThanOrEqual(footer.top - gap);
    expect(box.right).toBeLessThanOrEqual(viewport.width - pad);
  });
});
