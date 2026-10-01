import { useState } from 'react'

const PERIOD_OPTIONS = [
  ['day', 'Day', 'today', 'tomorrow'],
  ['week', 'Week', 'this_week', 'next_week'],
  ['month', 'Month', 'this_month', 'next_month'],
]

function ForecastChart({ forecast, current, next, mode, currency, formatMoney, formatCompactMoney, formatDate }) {
  const [selectedDate, setSelectedDate] = useState('')
  const context = mode === 'day' ? forecast.history.slice(-7).map((point) => ({
    ...point, actual_revenue: point.revenue, is_prediction: false, upper: point.revenue,
  })) : []
  const points = [...context, ...current.daily, ...next.daily]
  const actual = points.filter((point) => point.actual_revenue != null)
  const predicted = points.filter((point) => point.is_prediction)
  const selected = points.find((point) => point.date === selectedDate) || predicted[0]
  const first = Date.parse(points[0].date)
  const last = Date.parse(points[points.length - 1].date)
  const maximum = Math.max(1, ...points.map((point) => Math.max(Number(point.upper), Number(point.actual_revenue || 0)))) * 1.12
  const x = (date) => 80 + (Date.parse(date) - first) / (last - first) * 840
  const y = (value) => 215 - Number(value) / maximum * 175
  const line = (rows, field) => rows.map((point) => `${x(point.date)},${y(point[field])}`).join(' ')
  const band = `${line(predicted, 'upper')} ${line([...predicted].reverse(), 'lower')}`
  const labels = [points[0], points[Math.floor(points.length / 3)], points[Math.floor(points.length * 2 / 3)], points[points.length - 1]]
  const nextX = x(next.date_from)
  const hitRadius = Math.min(9, 840 / points.length / 2)
  return <>
    <div className="forecast-chart-scroll">
      <svg className="forecast-chart" viewBox="0 0 960 265" aria-label={`Actual and predicted daily revenue in ${currency}`}>
        {[0, 0.5, 1].map((fraction) => <g key={fraction}><line x1="80" x2="920" y1={y(maximum * fraction)} y2={y(maximum * fraction)} className="forecast-gridline" /><text x="68" y={y(maximum * fraction) + 4} textAnchor="end">{formatCompactMoney(maximum * fraction, currency)}</text></g>)}
        <polygon points={band} className="forecast-band" />
        <line x1={nextX} x2={nextX} y1="30" y2="215" className="forecast-boundary" />
        <text x={nextX - 8} y="23" textAnchor="end">{next.label}</text>
        <polyline points={line(actual, 'actual_revenue')} className="forecast-actual-line" />
        <polyline points={line(predicted, 'revenue')} className="forecast-estimate-line" />
        {points.map((point) => {
          const description = `${formatDate(point.date, true)}${point.actual_revenue != null ? `, actual ${formatMoney(point.actual_revenue, currency)}` : ''}${point.is_prediction ? `, predicted ${formatMoney(point.revenue, currency)}, range ${formatMoney(point.lower, currency)} to ${formatMoney(point.upper, currency)}` : ''}`
          return <g key={point.date} tabIndex="0" role="button" aria-label={description} onFocus={() => setSelectedDate(point.date)} onPointerEnter={() => setSelectedDate(point.date)} onClick={() => setSelectedDate(point.date)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedDate(point.date) } }}>
            <title>{description}</title>
            {point.actual_revenue != null && <><circle cx={x(point.date)} cy={y(point.actual_revenue)} r={hitRadius} className="forecast-hit-target" /><circle cx={x(point.date)} cy={y(point.actual_revenue)} r={point.date === selected.date ? 5 : 3} className="forecast-actual-dot" /></>}
            {point.is_prediction && <><circle cx={x(point.date)} cy={y(point.revenue)} r={hitRadius} className="forecast-hit-target" /><circle cx={x(point.date)} cy={y(point.revenue)} r={point.date === selected.date ? 5 : 3} className="forecast-estimate-dot" /></>}
          </g>
        })}
        {labels.map((point, index) => <text key={point.date} x={x(point.date)} y="246" textAnchor={index === 0 ? 'start' : index === labels.length - 1 ? 'end' : 'middle'}>{formatDate(point.date, true)}</text>)}
      </svg>
    </div>
    <small className="forecast-scroll-hint">Swipe the chart to explore all dates.</small>
    <div className="forecast-chart-caption"><div className="forecast-legend"><span><i className="recorded" />Actual</span><span><i className="projected" />Predicted</span><span><i className="range" />Estimated range</span></div><p aria-live="polite"><strong>{formatDate(selected.date, true)}</strong>{selected.actual_revenue != null && <> &middot; Actual {formatMoney(selected.actual_revenue, currency)}</>}{selected.is_prediction && <> &middot; Predicted {formatMoney(selected.revenue, currency)}<small>Range {formatMoney(selected.lower, currency)} &ndash; {formatMoney(selected.upper, currency)}</small></>}</p></div>
  </>
}

export default function RevenueForecast({ forecasts = {}, primaryCurrency, formatMoney, formatCompactMoney, formatDate }) {
  const [mode, setMode] = useState('day')
  const [selectedCurrency, setSelectedCurrency] = useState('')
  const currencies = Object.keys(forecasts)
  const currency = currencies.includes(selectedCurrency) ? selectedCurrency : currencies.includes(primaryCurrency) ? primaryCurrency : currencies[0]
  const forecast = forecasts[currency]
  const option = PERIOD_OPTIONS.find(([value]) => value === mode)
  const current = forecast?.periods?.[option[2]]
  const next = forecast?.periods?.[option[3]]
  const change = forecast?.weekly_change_percent
  return <section className="revenue-forecast" aria-label="Revenue forecast">
    <header><div><span className="forecast-kicker">Revenue outlook</span><h2>Revenue forecast</h2><p>Current and upcoming revenue for the selected hostel scope.</p></div><div className="forecast-controls">
      {currencies.length > 1 && <select aria-label="Forecast currency" value={currency} onChange={(event) => setSelectedCurrency(event.target.value)}>{currencies.map((item) => <option key={item}>{item}</option>)}</select>}
      <div role="group" aria-label="Forecast period">{PERIOD_OPTIONS.map(([value, label]) => <button type="button" key={value} aria-pressed={mode === value} className={mode === value ? 'active' : ''} onClick={() => setMode(value)}>{label}</button>)}</div>
    </div></header>
    {!forecast?.available || !current || !next ? <div className="forecast-empty"><strong>Building your revenue forecast</strong><p>{forecast?.reason || 'At least 14 completed days of paid revenue history are needed.'}</p>{forecast && <small>{forecast.history_days} completed days available for {currency}.</small>}</div> : <>
      <div className="forecast-metrics forecast-period-metrics">{[current, next].map((period, index) => <article className={index === 0 ? 'forecast-total' : ''} key={period.label}>
        <div className="forecast-period-heading"><h3>{period.label}</h3><span>{formatDate(period.date_from, true)}{period.days > 1 && <> &ndash; {formatDate(period.date_to, true)}</>}</span></div>
        <small>Predicted revenue</small><strong>{formatMoney(period.projected_revenue, currency)}</strong>
        <div className="forecast-period-range"><span>Estimated range</span><b>{formatMoney(period.lower_revenue, currency)} &ndash; {formatMoney(period.upper_revenue, currency)}</b></div>
        {period.actual_revenue != null ? <p className="forecast-period-actual"><i />Actual so far <b>{formatMoney(period.actual_revenue, currency)}</b></p> : <p className="forecast-period-future">Forecast for the upcoming {mode}.</p>}
      </article>)}</div>
      <ForecastChart key={`${currency}-${mode}`} forecast={forecast} current={current} next={next} mode={mode} currency={currency} formatMoney={formatMoney} formatCompactMoney={formatCompactMoney} formatDate={formatDate} />
      <div className="forecast-explanation"><div className="forecast-baseline"><span>Recent daily average <strong>{formatMoney(forecast.recent_daily_average, currency)}</strong></span><span>Weekly trend <strong className={change == null || change === 0 ? '' : change > 0 ? 'positive' : 'negative'}>{change == null ? 'New revenue' : `${change > 0 ? '+' : ''}${change.toFixed(1)}%`}</strong></span></div><p>Current totals include actual revenue earned so far plus predictions for the remaining time. The chart shows daily revenue; shaded areas show the estimated range. Weeks run Monday&ndash;Sunday, months follow the calendar, and dates use UTC.</p><details><summary>How the forecast works</summary><p>Uses {forecast.history_days} completed days of successful payments, from {formatDate(forecast.history_from, true)} to {formatDate(forecast.history_to, true)}, to estimate weekday patterns and recent growth. Today&apos;s partial revenue is shown as actual and sets a minimum for today&apos;s prediction. Completed dates show actuals, without invented past predictions. Currencies are calculated separately. The range widens into the future and illustrates uncertainty; it is not a statistical confidence interval.</p></details><details><summary>Daily revenue details</summary><div className="admin-data-table-wrap"><table className="admin-data-table"><thead><tr><th>Date</th><th>Actual</th><th>Predicted</th><th>Estimated range</th></tr></thead><tbody>{[...current.daily, ...next.daily].map((point) => <tr key={point.date}><td>{formatDate(point.date, true)}</td><td>{point.actual_revenue == null ? '--' : formatMoney(point.actual_revenue, currency)}</td><td>{point.is_prediction ? formatMoney(point.revenue, currency) : '--'}</td><td>{point.is_prediction ? <>{formatMoney(point.lower, currency)} &ndash; {formatMoney(point.upper, currency)}</> : '--'}</td></tr>)}</tbody></table></div></details></div>
    </>}
  </section>
}
