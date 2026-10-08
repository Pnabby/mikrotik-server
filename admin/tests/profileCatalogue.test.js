import assert from 'node:assert/strict'
import test from 'node:test'

import { profilesAcrossHostels } from '../src/utils/profileCatalogue.js'

const hostels = [{ router_id: 'main', name: 'Flint Main' }, { router_id: 'annex', name: 'Flint Annex' }]
const paid = { mikrotik_profile: 'paid', available_on_router: true, is_configured: true, rate_limit: '5M/10M' }

test('profiles missing from one hostel stay visible and have a usable source', () => {
  const [result] = profilesAcrossHostels([[paid], []], hostels)
  assert.equal(result.mikrotik_profile, 'paid')
  assert.equal(result.available_hostels, 1)
  assert.equal(result.hostel_count, 2)
  assert.equal(result.source_router_id, 'main')
  assert.equal(result.configuration_consistent, false)
  assert.equal(result.hostel_profiles[1].available_on_router, false)
  assert.equal(result.hostel_profiles[1].hostel_name, 'Flint Annex')
})

test('speed mismatches are visible even when the commercial settings match', () => {
  const [result] = profilesAcrossHostels([[paid], [{ ...paid, rate_limit: '5M/5M' }]], hostels)
  assert.ok(result.mixed_fields.includes('rate_limit'))
  assert.equal(result.configuration_consistent, false)
})

test('a source is selected from a router that actually has the profile', () => {
  const [result] = profilesAcrossHostels([[], [paid]], hostels)
  assert.equal(result.source_router_id, 'annex')
  assert.equal(result.available_on_router, true)
})
