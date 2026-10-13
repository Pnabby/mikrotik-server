import assert from 'node:assert/strict'
import test from 'node:test'

import { profilesAcrossHostels } from '../src/utils/profileCatalogue.js'
import { changedProfileDetails, mergeProfileDetails, profileDetailsFromForm, profileSaveRequest } from '../src/utils/profileEdits.js'

const form = {
  displayName: 'Weekly', description: 'A weekly plan', amount: '10.00', currency: 'GHS',
  durationValue: 1, durationUnit: 'weeks', dataLimitGb: 1, deviceLimit: 2,
  downloadSpeed: '10 Mbps', isPromotional: false, isVisible: true, groupId: 'weekly-group',
  applyRouterSettings: false, sharedUsers: 2, unlimitedSharedUsers: false,
}
const profile = {
  ...profileDetailsFromForm(form, {}), mikrotik_profile: 'paid', is_configured: true,
  available_on_router: true, rate_limit: '5M/10M', shared_users: 2, session_timeout: '1h',
}

test('a price edit uses PATCH and sends only the edited price', () => {
  const updated = { ...form, amount: 15 }
  const changes = changedProfileDetails(form, updated, profile)
  const request = profileSaveRequest(profile, profileDetailsFromForm(updated, profile), changes)
  assert.deepEqual(request, { method: 'PATCH', payload: { amount: '15.00' } })
})

test('a price edit with mixed hostel settings preserves blank and false placeholders', () => {
  const mixedProfile = { ...profile, bulk_mode: true,
    mixed_fields: ['display_name', 'description', 'device_limit', 'is_visible', 'is_promotional'],
  }
  const initial = { ...form, displayName: '', description: '', deviceLimit: '',
    isVisible: false, isPromotional: false,
  }
  assert.deepEqual(changedProfileDetails(initial, { ...initial, amount: 20 }, mixedProfile, ['amount']),
    { amount: '20.00' })
})

test('a mixed optional field can be explicitly cleared across hostels', () => {
  const mixedProfile = { ...profile, bulk_mode: true, mixed_fields: ['description'] }
  const initial = { ...form, description: '' }
  assert.deepEqual(changedProfileDetails(initial, initial, mixedProfile, ['description']),
    { description: null })
})

test('equivalent prices, duration units, whitespace and reverted edits send no changes', () => {
  const updated = { ...form, amount: 10, displayName: ' Weekly ', durationValue: 7, durationUnit: 'days' }
  assert.deepEqual(changedProfileDetails(form, updated, profile, ['amount', 'displayName', 'durationUnit']), {})
})

test('the database result updates the catalogue while preserving router observations', () => {
  const updated = mergeProfileDetails(profile, { amount: '15.00', download_speed: null }, { amount: '15.00' })
  assert.equal(updated.amount, '15.00')
  assert.equal(updated.download_speed, '10 Mbps')
  assert.equal(updated.rate_limit, '5M/10M')
  assert.equal(updated.available_on_router, true)
  assert.equal(updated.shared_users, 2)
  assert.equal(updated.session_timeout, '1h')
})

test('applying router settings uses PUT while preserving each hostels commercial terms', () => {
  const routerSettings = { rate_limit: '5M/20M', shared_users: 3 }
  const payload = { ...profileDetailsFromForm(form, profile), router_settings: routerSettings,
    source_router_id: 'main',
  }
  const other = { ...profile, display_name: 'Annex Weekly', amount: '12.00', is_visible: false,
    duration_seconds: 86400, group_id: 'annex-group',
  }
  const request = profileSaveRequest(other, payload, { amount: '15.00' })
  assert.equal(request.method, 'PUT')
  assert.deepEqual(request.payload.router_settings, routerSettings)
  assert.equal(request.payload.display_name, 'Annex Weekly')
  assert.equal(request.payload.amount, '15.00')
  assert.equal(request.payload.is_visible, false)
  assert.equal(request.payload.duration_seconds, 86400)
  assert.equal(request.payload.group_id, 'annex-group')
})

test('an unconfigured or missing profile keeps the configuration and creation path', () => {
  const payload = { ...profileDetailsFromForm(form, profile),
    router_settings: { rate_limit: '5M/10M' }, source_router_id: 'main',
  }
  assert.deepEqual(profileSaveRequest({ is_configured: false }, payload, { amount: '15.00' }),
    { method: 'PUT', payload })
})

test('all-hostel save results retain each hostels different router settings', () => {
  const hostels = [{ router_id: 'main' }, { router_id: 'annex' }]
  const other = { ...profile, rate_limit: '2M/8M', shared_users: 4, display_name: 'Annex Weekly' }
  const results = [profile, other].map((previous) => [
    mergeProfileDetails(previous, { amount: '20.00' }, { amount: '20.00' }),
  ])
  const [combined] = profilesAcrossHostels(results, hostels)
  assert.equal(combined.amount, '20.00')
  assert.ok(combined.mixed_fields.includes('rate_limit'))
  assert.ok(combined.mixed_fields.includes('display_name'))
  assert.equal(combined.hostel_profiles[0].shared_users, 2)
  assert.equal(combined.hostel_profiles[1].shared_users, 4)
})
