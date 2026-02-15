const PREFIX = "cc_mock";

type MockBucket = {
  projects: unknown[];
  channels: unknown[];
  posts: unknown[];
};

function storageKey(tenantId: string): string {
  return `${PREFIX}_${tenantId}`;
}

function readBucket(tenantId: string): MockBucket {
  try {
    const raw = localStorage.getItem(storageKey(tenantId));
    if (!raw) {
      return { projects: [], channels: [], posts: [] };
    }

    const parsed = JSON.parse(raw) as Partial<MockBucket>;
    return {
      projects: Array.isArray(parsed.projects) ? parsed.projects : [],
      channels: Array.isArray(parsed.channels) ? parsed.channels : [],
      posts: Array.isArray(parsed.posts) ? parsed.posts : [],
    };
  } catch {
    return { projects: [], channels: [], posts: [] };
  }
}

function writeBucket(tenantId: string, bucket: MockBucket): void {
  localStorage.setItem(storageKey(tenantId), JSON.stringify(bucket));
}

export function getMockCollection<T>(tenantId: string, key: keyof MockBucket): T[] {
  const bucket = readBucket(tenantId);
  return (bucket[key] as T[]) ?? [];
}

export function addMockItem<T extends { id: string }>(tenantId: string, key: keyof MockBucket, item: T): T {
  const bucket = readBucket(tenantId);
  const next = [item, ...(bucket[key] as T[])];
  writeBucket(tenantId, { ...bucket, [key]: next });
  return item;
}

export function updateMockItem<T extends { id: string }>(
  tenantId: string,
  key: keyof MockBucket,
  id: string,
  updater: (current: T) => T
): T | null {
  const bucket = readBucket(tenantId);
  const collection = bucket[key] as T[];
  const index = collection.findIndex((row) => row.id === id);
  if (index === -1) {
    return null;
  }

  const nextItem = updater(collection[index]);
  const nextCollection = [...collection];
  nextCollection[index] = nextItem;
  writeBucket(tenantId, { ...bucket, [key]: nextCollection });
  return nextItem;
}
