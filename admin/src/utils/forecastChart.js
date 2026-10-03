export function forecastChartPoints(forecast, current, next) {
  const history = (forecast.history || [])
    .filter((point) => point.date < current.date_from)
    .map((point) => ({
      date: point.date,
      revenue: point.predicted_revenue ?? point.revenue,
      lower: point.lower ?? point.revenue,
      upper: point.upper ?? point.revenue,
      actual_revenue: point.revenue,
      is_prediction: point.predicted_revenue != null && point.lower != null && point.upper != null,
    }))
  return [...new Map([...history, ...current.daily, ...next.daily]
    .map((point) => [point.date, point])).values()]
    .sort((left, right) => left.date.localeCompare(right.date))
}

export function forecastSeriesSegments(points, includesPoint) {
  const segments = []
  let segment = []
  for (const point of points) {
    if (includesPoint(point)) {
      segment.push(point)
    } else if (segment.length) {
      segments.push(segment)
      segment = []
    }
  }
  if (segment.length) segments.push(segment)
  return segments
}
