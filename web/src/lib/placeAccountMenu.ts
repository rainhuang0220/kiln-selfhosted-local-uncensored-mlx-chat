export type Box = {
  top: number;
  right: number;
  bottom: number;
  left: number;
};

export type MenuPlacement = {
  left: number;
  width: number;
  bottom: number;
  maxHeight: number;
};

const PAD = 8;
const GAP = 8;
const PREFERRED_WIDTH = 220;

export function placeAccountMenu({
  viewport,
  footer,
  trigger,
  preferredWidth = PREFERRED_WIDTH,
  pad = PAD,
  gap = GAP,
}: {
  viewport: { width: number; height: number };
  footer: Box;
  trigger: Box;
  preferredWidth?: number;
  pad?: number;
  gap?: number;
}): MenuPlacement {
  const width = Math.min(preferredWidth, Math.max(0, viewport.width - pad * 2));
  let left = trigger.left;
  if (left + width > viewport.width - pad) left = viewport.width - pad - width;
  if (left < pad) left = pad;

  return {
    left: Math.round(left),
    width: Math.round(width),
    bottom: Math.round(viewport.height - footer.top + gap),
    maxHeight: Math.max(0, Math.round(footer.top - gap - pad)),
  };
}
