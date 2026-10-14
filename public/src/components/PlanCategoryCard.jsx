export default function PlanCategoryCard({ href, name, planCount, price }) {
  return (
    <a className="plan-category-card site-card" href={href}>
      <span className="category-accent" aria-hidden="true" />
      <div className="category-title">
        <h3>{name}</h3>
        <span className="category-arrow" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12h14m-5-5 5 5-5 5" /></svg></span>
      </div>
      <p>{planCount} plan{planCount === 1 ? '' : 's'}</p>
      <div className="category-footer">
        <div><span>From</span><strong>{price}</strong></div>
        <span>View plans</span>
      </div>
    </a>
  )
}
