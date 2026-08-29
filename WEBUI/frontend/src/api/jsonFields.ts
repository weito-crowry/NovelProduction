export function formatStoredJson(value: string): string {
  try {
    return JSON.stringify(JSON.parse(value) as unknown, null, 2);
  } catch {
    return value;
  }
}

export function parseJsonEditor(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new Error("Enter valid JSON.");
  }
}

export function parseForeshadowingNotesEditor(text: string): unknown[] {
  const value = parseJsonEditor(text);
  if (!Array.isArray(value)) {
    throw new Error("Foreshadowing notes must be a JSON array.");
  }
  return value;
}
