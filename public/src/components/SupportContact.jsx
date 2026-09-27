import { useEffect, useState } from 'react'

import supportIcon from '../assets/customer-service.png'
import { ChatIcon, CloseIcon, PhoneIcon, ShieldIcon } from './Icons'
import { getSupportSettings } from '../services/supportApi'

export default function SupportContact() {
  const [support, setSupport] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let active = true
    getSupportSettings()
      .then((result) => { if (active) setSupport(result) })
      .catch(() => {})
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!open) return undefined
    function closeOnEscape(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  useEffect(() => {
    function openFromLink() {
      setOpen(true)
    }
    window.addEventListener('vlad:open-support', openFromLink)
    return () => window.removeEventListener('vlad:open-support', openFromLink)
  }, [])

  if (!support?.phone_number && !support?.whatsapp_url) return null
  const telephone = support.phone_number?.replace(/[^+\d]/g, '')

  return (
    <>
      <button className="support-launcher" type="button" aria-label="Open help and support" aria-expanded={open} onClick={() => setOpen(true)}>
        <img src={supportIcon} alt="" />
      </button>

      {open && (
        <div className="support-modal-backdrop" role="presentation" onMouseDown={() => setOpen(false)}>
          <section className="support-modal" role="dialog" aria-modal="true" aria-labelledby="support-modal-title" onMouseDown={(event) => event.stopPropagation()}>
            <button autoFocus className="support-modal-close" type="button" aria-label="Close help and support" onClick={() => setOpen(false)}><CloseIcon /></button>
            <span className="support-modal-icon"><img src={supportIcon} alt="" /></span>
            <span className="support-modal-label">Help &amp; support</span>
            <h2 id="support-modal-title">How can we help?</h2>
            <p>Choose one of the available support options below.</p>

            <div className="support-modal-actions">
              {support.phone_number && (
                <a className="support-modal-phone" href={`tel:${telephone}`}>
                  <PhoneIcon />
                  <span><small>Call support</small><strong>{support.phone_number}</strong></span>
                </a>
              )}
              {support.whatsapp_url && (
                <a className="support-modal-whatsapp" href={support.whatsapp_url} rel="noreferrer" target="_blank">
                  <ChatIcon />
                  <span><small>Send a message</small><strong>Open WhatsApp</strong></span>
                </a>
              )}
            </div>

            <div className="support-modal-note"><ShieldIcon /><span>Support will never ask for your PIN or verification code.</span></div>
            <a className="support-icon-credit" href="https://www.flaticon.com/free-icons/customer-service" title="customer service icons" rel="noreferrer" target="_blank">Customer service icon created by Cuputo - Flaticon</a>
          </section>
        </div>
      )}
    </>
  )
}
