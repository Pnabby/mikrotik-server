import assert from 'node:assert/strict'
import test from 'node:test'

import { forecastChartPoints, forecastSeriesSegments } from '../src/utils/forecastChart.js'

const historical = (date, prediction = null) => ({
  date, revenue: 200, predicted_revenue: prediction,
  lower: prediction == null ? null : 80,
  upper: prediction == null ? null : 120,
})
const daily = (date) => ({
  date, revenue: 100, lower: 80, upper: 120, actual_revenue: null, is_prediction: true,
})

test('the chart includes every historical prediction and range beside actual revenue', () => {
  const history = Array.from({ length: 28 }, (_, index) =>
    historical(`2026-09-${String(index + 1).padStart(2, '0')}`, 100))
  const current = { date_from: '2026-10-01', daily: [daily('2026-10-01')] }
  const next = { daily: [daily('2026-10-02')] }
  const points = forecastChartPoints({ history }, current, next)
  assert.equal(points.length, 30)
  assert.deepEqual(points[0], {
    date: '2026-09-01', revenue: 100, lower: 80, upper: 120,
    actual_revenue: 200, is_prediction: true,
  })
  assert.ok(points.slice(0, 28).every((point) => point.is_prediction))
})

test('current period baselines take precedence without duplicating history dates', () => {
  const current = { date_from: '2026-09-28', daily: [daily('2026-09-28'), daily('2026-09-29')] }
  const next = { daily: [daily('2026-09-30')] }
  const points = forecastChartPoints({ history: [historical('2026-09-27', 90), historical('2026-09-28', 500)] }, current, next)
  assert.deepEqual(points.map((point) => point.date), ['2026-09-27', '2026-09-28', '2026-09-29', '2026-09-30'])
  assert.equal(points[1].revenue, 100)
})

test('missing predictions stay absent and break the range instead of bridging the gap', () => {
  const current = { date_from: '2026-10-01', daily: [daily('2026-10-01')] }
  const points = forecastChartPoints({ history: [historical('2026-09-28', 100), historical('2026-09-29'), historical('2026-09-30', 0)] }, current, { daily: [] })
  assert.equal(points[1].is_prediction, false)
  assert.equal(points[2].revenue, 0)
  const segments = forecastSeriesSegments(points, (point) => point.is_prediction)
  assert.deepEqual(segments.map((segment) => segment.map((point) => point.date)), [['2026-09-28'], ['2026-09-30', '2026-10-01']])
})
