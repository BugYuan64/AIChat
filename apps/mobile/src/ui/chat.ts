interface EnterEvent { key?: string; keyCode?: number; shiftKey?: boolean; ctrlKey?: boolean; altKey?: boolean; metaKey?: boolean; isComposing?: boolean }
export function isNearMessageBottom(scrollTop: number, scrollHeight: number, viewportHeight: number): boolean { return scrollHeight - scrollTop - viewportHeight <= 96; }
export function shouldSendOnEnter(event: EnterEvent): boolean {
  return event.key === 'Enter' && event.keyCode !== 229 && !event.isComposing && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey;
}
export function filterConversations<T extends { title?: string; direct_peer?: { display_name?: string; handle?: string } }>(items: T[], query: string): T[] {
  const term = query.trim().toLocaleLowerCase();
  return items.filter((item) => !term || [item.title, item.direct_peer?.display_name, item.direct_peer?.handle].some((value) => value?.toLocaleLowerCase().includes(term)));
}
