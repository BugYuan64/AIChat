export type LayoutMode = 'mobile' | 'compact' | 'desktop';

export const COMPACT_BREAKPOINT = 768;
export const DESKTOP_BREAKPOINT = 900;
export const WIDE_BREAKPOINT = 1100;

export function layoutMode(width: number): LayoutMode {
  if (!Number.isFinite(width) || width < COMPACT_BREAKPOINT) return 'mobile';
  if (width < DESKTOP_BREAKPOINT) return 'compact';
  return 'desktop';
}

export function isDesktopWidth(width: number): boolean {
  return layoutMode(width) === 'desktop';
}

export function isWideDesktopWidth(width: number): boolean {
  return Number.isFinite(width) && width >= WIDE_BREAKPOINT;
}
