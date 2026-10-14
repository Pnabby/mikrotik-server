export default function PageHero({ children, className = '', description, eyebrow, id, title, titleId }) {
  return (
    <section className={`site-hero ${className}`} id={id}>
      <svg className="hero-signal" viewBox="0 0 360 360" fill="none" aria-hidden="true">
        <circle cx="180" cy="180" r="58" />
        <circle cx="180" cy="180" r="106" />
        <circle cx="180" cy="180" r="154" />
        <circle cx="180" cy="180" r="202" />
      </svg>
      <div className="hero-content">
        {eyebrow && <span className="hero-eyebrow">{eyebrow}</span>}
        <h1 id={titleId}>{title}</h1>
        {description && <p className="hero-description">{description}</p>}
        {children}
      </div>
    </section>
  )
}
