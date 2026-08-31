"use client";

import type { MemoryEntryDTO } from "@/types/memory";

export function MemoryEntryList({
  items,
  empty,
  onSelect,
  onCreate,
}: {
  items: MemoryEntryDTO[];
  empty: string;
  onSelect?: (item: MemoryEntryDTO) => void;
  onCreate?: () => void;
}) {
  return (
    <div className="memory-list">
      {onCreate && (
        <div className="knowledge-page__actions">
          <button type="button" onClick={onCreate}>新建记忆</button>
        </div>
      )}
      {items.length === 0 && <p className="knowledge-empty-copy">{empty}</p>}
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <button type="button" onClick={() => onSelect?.(item)}>
              <strong>{item.title || item.content.slice(0, 24)}</strong>
              <span>{item.content}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
