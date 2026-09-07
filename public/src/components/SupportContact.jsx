import { useEffect, useState } from 'react'

import { getSupportSettings } from '../services/supportApi'

export default function SupportContact() {
  const [support, setSupport] = useState(null)

  useEffect(() => {
    let active = true
    getSupportSettings()
      .then((result) => { if (active) setSupport(result) })
      .catch(() => {})
    return () => { active = false }
  }, [])

  if (!support?.phone_number && !support?.whatsapp_url) return null
  const telephone = support.phone_number?.replace(/[^+\d]/g, '')

  return (
    <aside className="public-support-contact" aria-label="Help and support">
      <span>Need help?</span>
      <div>
        {support.phone_number && <a className="support-phone" href={`tel:${telephone}`}><i aria-hidden="true">☎</i>{support.phone_number}</a>}
        {support.whatsapp_url && <a className="support-whatsapp" href={support.whatsapp_url} rel="noreferrer" target="_blank"><i aria-hidden="true">◉</i>WhatsApp</a>}
      </div>
    </aside>
  )
}
