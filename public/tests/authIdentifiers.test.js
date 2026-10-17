import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeLoginIdentifier, normalizeRecoveryIdentifier } from '../src/utils/authIdentifiers.js'

test('sign-in accepts usernames and formatted phone numbers', () => {
  for (const value of ['024 123 4567', '024-123-4567', '233241234567', '+233 (24) 123 4567']) {
    assert.equal(normalizeLoginIdentifier(value), '+233241234567')
  }
  assert.equal(normalizeLoginIdentifier(' Vlad123 '), 'vlad123')
  assert.equal(normalizeLoginIdentifier('0vlad'), '0vlad')
  assert.equal(normalizeLoginIdentifier('+12025550123'), '+12025550123')
})

test('recovery preserves hyphens and plus tags in email addresses', () => {
  assert.equal(normalizeRecoveryIdentifier(' Ama-Boateng+wifi@Example.com '), 'ama-boateng+wifi@example.com')
  assert.equal(normalizeRecoveryIdentifier('024 123 4567'), '+233241234567')
})

test('invalid recovery details and malformed usernames are rejected', () => {
  for (const value of ['', 'no-at-sign', '024123', 'user@', 'user name@example.com']) {
    assert.equal(normalizeRecoveryIdentifier(value), '')
  }
  for (const value of ['', 'ab', 'user name', '+0233241234567', 'user@example.com']) {
    assert.equal(normalizeLoginIdentifier(value), '')
  }
})
