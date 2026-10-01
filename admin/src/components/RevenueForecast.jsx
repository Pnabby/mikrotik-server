import { useState } from 'react'

function ForecastChart({ forecast, horizon, currency, formatMoney, formatCompactMoney, formatDate }) {
  const [selectedDate, setSelectedDate] = useState('')
  const history = forecast.history.slice(-14)
  const points = [
    ...history.map((point) => ({ ...point, kind: 'Recorded' })),
    ...horizon.daily.map((point) => ({ ...point, kind: 'Projected' })),
  ]
  const selected = points.find((point) => point.date === selectedDate) || points[points.length - 1]
  const first = Date.parse(points[0].date)
  const last = Date.parse(points[points.length - 1].date)
  const maximum = Math.max(1, ...points.map((point) => Number(point.upper ?? point.revenue))) * 1.12
  const x = (date) => 80 + (Date.parse(date) - first) / (last - first) * 840
  const y = (value) => 215 - Number(value) / maximum * 175
  const line = (rows, field) => rows.map((point) => `${x(point.date)},${y(point[field])}`).join(' ')
  const band = `${line(horizon.daily, 'upper')} ${line([...horizon.daily].reverse(), 'lower')}`
  const labels = [history[0], history[history.length - 1], horizon.daily[Math.floor(horizon.days / 2)], horizon.daily[horizon.days - 1]].filter((point, index, rows) => rows.findIndex((item) => item.date === point.date) === index)
  const todayX = x(new Date(Date.parse(horizon.date_from) - 86400000).toISOString().slice(0, 10))
  return <>
    <div className="forecast-chart-scroll">
      <svg className="forecast-chart" viewBox="0 0 960 265" aria-label={`Recorded and forecast daily revenue in ${currency}`}>
        {[0, 0.5, 1].map((fraction) => <g key={fraction}><line x1="80" x2="920" y1={y(maximum * fraction)} y2={y(maximum * fraction)} className="forecast-gridline" /><text x="68" y={y(maximum * fraction) + 4} textAnchor="end">{formatCompactMoney(maximum * fraction, currency)}</text></g>)}
        {horizon.days === 1 ? <line x1={x(horizon.daily[0].date)} x2={x(horizon.daily[0].date)} y1={y(horizon.daily[0].upper)} y2={y(horizon.daily[0].lower)} className="forecast-single-range" /> : <polygon points={band} className="forecast-band" />}
        <line x1={todayX} x2={todayX} y1="30" y2="215" className="forecast-boundary" />
        <text x={todayX + 8} y="23">Forecast</text>
        <polyline points={line(history, 'revenue')} className="forecast-actual-line" />
        <polyline points={line(horizon.daily, 'revenue')} className="forecast-estimate-line" />
        {points.map((point) => <g key={point.date} tabIndex="0" role="button" aria-label={`${formatDate(point.date, true)}: ${point.kind.toLowerCase()} ${formatMoney(point.revenue, currency)}`} onFocus={() => setSelectedDate(point.date)} onPointerEnter={() => setSelectedDate(point.date)} onClick={() => setSelectedDate(point.date)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedDate(point.date) } }}>
          <title>{formatDate(point.date, true)}: {formatMoney(point.revenue, currency)} ({point.kind.toLowerCase()})</title>
          <circle cx={x(point.date)} cy={y(point.revenue)} r="9" className="forecast-hit-target" />
          <circle cx={x(point.date)} cy={y(point.revenue)} r={point.date === selected.date ? 5 : 3} className={point.kind === 'Recorded' ? 'forecast-actual-dot' : 'forecast-estimate-dot'} />
        </g>)}
        {labels.map((point, index) => <text key={point.date} x={x(point.date)} y="246" textAnchor={index === 0 ? 'start' : index === labels.length - 1 ? 'end' : 'middle'}>{formatDate(point.date, true)}</text>)}
      </svg>
    </div>
    <small className="forecast-scroll-hint">Swipe the chart to explore upcoming dates.</small>
    <div className="forecast-chart-caption"><div className="forecast-legend"><span><i className="recorded" />Recorded</span><span><i className="projected" />Projected</span><span><i className="range" />Estimated range</span></div><p aria-live="polite"><strong>{formatDate(selected.date, true)}</strong> {selected.kind}: {formatMoney(selected.revenue, currency)}</p></div>
  </>
}

export default function RevenueForecast({ forecasts = {}, primaryCurrency, formatMoney, formatCompactMoney, formatDate }) {
  const [days, setDays] = useState(1)
  const [selectedCurrency, setSelectedCurrency] = useState('')
  const currencies = Object.keys(forecasts)
  const currency = currencies.includes(selectedCurrency) ? selectedCurrency : currencies.includes(primaryCurrency) ? primaryCurrency : currencies[0]
  const forecast = forecasts[currency]
  const horizon = forecast?.horizons?.[days]
  const change = forecast?.weekly_change_percent
  return <section className="revenue-forecast" aria-label="Revenue forecast">
    <header><div><span className="forecast-kicker">Looking ahead</span><h2>Revenue forecast</h2><p>Recent payment trends for the selected hostel scope.</p></div><div className="forecast-controls">
      {currencies.length > 1 && <select aria-label="Forecast currency" value={currency} onChange={(event) => setSelectedCurrency(event.target.value)}>{currencies.map((item) => <option key={item}>{item}</option>)}</select>}
      <div role="group" aria-label="Forecast period">{[[1, 'Day', 'Tomorrow'], [7, 'Week', 'Next 7 days'], [30, 'Month', 'Next 30 days']].map(([value, label, description]) => <button type="button" key={value} title={description} aria-label={`${label} forecast: ${description.toLowerCase()}`} aria-pressed={days === value} className={days === value ? 'active' : ''} onClick={() => setDays(value)}>{label}</button>)}</div>
    </div></header>
    {!forecast?.available || !horizon ? <div className="forecast-empty"><strong>Building your revenue forecast</strong><p>{forecast?.reason || 'At least 14 completed days of paid revenue history are needed.'}</p>{forecast && <small>{forecast.history_days} completed days available for {currency}.</small>}</div> : <>
      <div className="forecast-metrics">
        <article className="forecast-total"><small>Projected revenue ({days === 1 ? 'tomorrow' : `next ${days} days`})</small><strong>{formatMoney(horizon.projected_revenue, currency)}</strong><span>{formatDate(horizon.date_from, true)}{horizon.days > 1 && <> &ndash; {formatDate(horizon.date_to, true)}</>}</span></article>
        <article><small>Estimated range</small><strong>{formatMoney(horizon.lower_revenue, currency)} &ndash; {formatMoney(horizon.upper_revenue, currency)}</strong><span>Reflects recent daily variation</span></article>
        <article><small>Recent daily average</small><strong>{formatMoney(forecast.recent_daily_average, currency)}</strong><span>Last 7 completed days</span></article>
        <article><small>Weekly revenue trend</small><strong className={change == null || change === 0 ? '' : change > 0 ? 'positive' : 'negative'}>{change == null ? 'New revenue' : `${change > 0 ? '+' : ''}${change.toFixed(1)}%`}</strong><span>Last 7 days vs the previous 7</span></article>
      </div>
      <ForecastChart key={`${currency}-${days}`} forecast={forecast} horizon={horizon} currency={currency} formatMoney={formatMoney} formatCompactMoney={formatCompactMoney} formatDate={formatDate} />
      <div className="forecast-explanation"><p>Based on {forecast.history_days} completed days, {formatDate(forecast.history_from, true)} &ndash; {formatDate(forecast.history_to, true)}. Today is excluded. Forecasts start tomorrow and use recent history regardless of the reporting period above.</p><details><summary>How the forecast works</summary><p>Successful payments are grouped by weekday and adjusted for the latest weekly trend. Large changes are limited and gradually softened over time. Zero-revenue days are included, and currencies are calculated separately. The range illustrates daily variation and widens further into the future; it is not a guaranteed outcome or a statistical confidence interval.</p></details><details><summary>Daily estimates</summary><div className="admin-data-table-wrap"><table className="admin-data-table"><thead><tr><th>Date</th><th>Projected revenue</th><th>Estimated range</th></tr></thead><tbody>{horizon.daily.map((point) => <tr key={point.date}><td>{formatDate(point.date, true)}</td><td>{formatMoney(point.revenue, currency)}</td><td>{formatMoney(point.lower, currency)} &ndash; {formatMoney(point.upper, currency)}</td></tr>)}</tbody></table></div></details></div>
    </>}
  </section>
}
