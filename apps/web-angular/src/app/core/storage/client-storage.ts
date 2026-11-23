export interface ClientStorage {
  get<T>(key: string): T | null;
  set<T>(key: string, value: T): void;
  remove(key: string): void;
  clear(): void;
}

export class LocalStorageClient implements ClientStorage {
  get<T>(key: string): T | null {
    try {
      const item = localStorage.getItem(key);
      return item ? (JSON.parse(item) as T) : null;
    } catch {
      return null;
    }
  }

  set<T>(key: string, value: T): void {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      console.error(`Failed to save ${key} to storage`, e);
    }
  }

  remove(key: string): void {
    try {
      localStorage.removeItem(key);
    } catch (e) {
      console.error(`Failed to remove ${key} from storage`, e);
    }
  }

  clear(): void {
    try {
      localStorage.clear();
    } catch (e) {
      console.error('Failed to clear storage', e);
    }
  }
}
