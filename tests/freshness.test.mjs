import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isStale, offlineStatus } from '../skybrief/src/services/freshness.ts';
const policy = {isStale, offlineStatus};
test('missing source timestamps are stale', () => assert.equal(policy.isStale(undefined, 100), true));
test('future timestamps are stale', () => assert.equal(policy.isStale('2026-01-02T00:00:00Z', 100, Date.parse('2026-01-01T00:00:00Z')), true));
test('fresh timestamps are not stale', () => assert.equal(policy.isStale('2026-01-01T00:00:00Z', 1000, Date.parse('2026-01-01T00:00:00Z') + 500), false));
test('expired timestamps are stale', () => assert.equal(policy.isStale('2026-01-01T00:00:00Z', 1000, Date.parse('2026-01-01T00:00:00Z') + 1001), true));
test('missing data cannot be treated as verified go', () => assert.equal(policy.offlineStatus(), 'caution'));