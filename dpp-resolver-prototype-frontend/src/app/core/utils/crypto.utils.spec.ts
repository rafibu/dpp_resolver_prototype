import { describe, it, expect } from 'vitest';
import { canonicalize, sha256 } from './crypto.utils';

describe('CryptoUtils', () => {
  describe('canonicalize', () => {
    it('should sort keys alphabetically', () => {
      const input = { z: 1, a: 2, m: 3 };
      const output = canonicalize(input);
      expect(output).toBe('{"a":2,"m":3,"z":1}');
    });

    it('should handle nested objects', () => {
      const input = { b: { y: 1, x: 2 }, a: 3 };
      const output = canonicalize(input);
      expect(output).toBe('{"a":3,"b":{"x":2,"y":1}}');
    });

    it('should handle arrays', () => {
      const input = { a: [3, 2, 1], b: 0 };
      const output = canonicalize(input);
      expect(output).toBe('{"a":[3,2,1],"b":0}');
    });
  });

  describe('sha256', () => {
    it('should produce consistent hash', async () => {
      const input = '{"a":1}';
      const hash1 = await sha256(input);
      const hash2 = await sha256(input);
      expect(hash1).toBe(hash2);
      expect(hash1.length).toBe(64);
    });
  });
});
