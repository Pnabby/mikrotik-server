import assert from 'node:assert/strict'
import test from 'node:test'

import { getPlanStatus } from '../src/utils/planStatus.js'

const currentPlan = { status: 'active', expires_at: null }
const routerStatus = { disabled: false, total_data_left_bytes: 1, expiry_date: null }
const now = Date.parse('2026-10-09T00:00:00Z')

test('a disabled router user has an exhausted plan despite an active stored subscription and remaining data', () => {
  assert.equal(getPlanStatus(currentPlan, { ...routerStatus, disabled: true }, 'ready', now), 'exhausted')
  assert.equal(getPlanStatus(currentPlan, { ...routerStatus, disabled: true, total_data_left_bytes: 0 }, 'ready', now), 'exhausted')
})

test('an enabled router user with remaining allowance has an active plan even without connected devices', () => {
  assert.equal(getPlanStatus(currentPlan, { ...routerStatus, connected_devices_count: 0 }, 'ready', now), 'active')
  assert.equal(getPlanStatus(currentPlan, { ...routerStatus, total_data_left_bytes: null }, 'ready', now), 'active')
})

test('a failed router check cannot use stale enabled status to claim the plan is active', () => {
  assert.equal(getPlanStatus(currentPlan, routerStatus, 'error', now), 'unavailable')
  assert.equal(getPlanStatus(currentPlan, null, 'error', now), 'unavailable')
  assert.equal(getPlanStatus(currentPlan, { total_data_left_bytes: 1 }, 'ready', now), 'unavailable')
})

test('refreshing router status shows checking until the latest result arrives', () => {
  assert.equal(getPlanStatus(currentPlan, routerStatus, 'loading', now), 'checking')
  assert.equal(getPlanStatus(currentPlan, { ...routerStatus, disabled: true }, 'ready', now), 'exhausted')
})

test('an enabled user with no remaining data or an expired plan is exhausted', () => {
  assert.equal(getPlanStatus(currentPlan, { ...routerStatus, total_data_left_bytes: 0 }, 'ready', now), 'exhausted')
  assert.equal(getPlanStatus(currentPlan, { ...routerStatus, expiry_date: '2026-10-09 00:00:00' }, 'ready', now), 'exhausted')
  assert.equal(getPlanStatus({ expires_at: '2026-10-08T23:00:00Z' }, routerStatus, 'ready', now), 'exhausted')
})

test('the live router expiry takes precedence over stored expiry', () => {
  assert.equal(getPlanStatus(
    { expires_at: '2026-10-08T23:00:00Z' },
    { ...routerStatus, expiry_date: '2026-10-10 00:00:00' }, 'ready', now,
  ), 'active')
})

test('a customer without a plan is inactive', () => {
  assert.equal(getPlanStatus(null, routerStatus, 'ready', now), 'inactive')
})
