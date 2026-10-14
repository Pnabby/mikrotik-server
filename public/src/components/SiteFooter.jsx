export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <p>Need help with your account or a purchase? Contact <a href="#help-and-support" onClick={(event) => {
        event.preventDefault()
        window.dispatchEvent(new Event('vlad:open-support'))
      }}>help and support</a>.</p>
    </footer>
  )
}
