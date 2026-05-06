export function deepEqual(valueA: unknown, valueB: unknown): boolean {
  if (Object.is(valueA, valueB)) {
    return true;
  }

  if (typeof valueA !== typeof valueB) {
    return false;
  }

  if (valueA === null || valueB === null) {
    return false;
  }

  if (typeof valueA !== 'object') {
    return false;
  }

  if (Array.isArray(valueA) || Array.isArray(valueB)) {
    if (!Array.isArray(valueA) || !Array.isArray(valueB)) {
      return false;
    }

    if (valueA.length !== valueB.length) {
      return false;
    }

    return valueA.every((item, index) => deepEqual(item, valueB[index]));
  }

  const objectA = valueA as Record<string, unknown>;
  const objectB = valueB as Record<string, unknown>;

  const keysA = Object.keys(objectA);
  const keysB = Object.keys(objectB);

  if (keysA.length !== keysB.length) {
    return false;
  }

  return keysA.every(key =>
    Object.prototype.hasOwnProperty.call(objectB, key) &&
    deepEqual(objectA[key], objectB[key])
  );
}
