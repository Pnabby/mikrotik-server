import { useEffect, useRef, useState } from 'react'
import prices from '../../image.png'
import './price-notice.css'

export default function PriceNotice() {
  const [open, setOpen] = useState(false)
  const dialog = useRef(null)
  useEffect(() => {
    if (open) dialog.current?.showModal()
    else dialog.current?.close()
  }, [open])
  return <>
    <div className="price-notice"><span>New WiFi prices effective 10 October 2026.</span><button type="button" onClick={() => setOpen(true)}>View prices</button></div>
    <dialog ref={dialog} className="price-notice-dialog" aria-labelledby="price-notice-title" onCancel={() => setOpen(false)} onClick={(event) => { if (event.target === event.currentTarget) setOpen(false) }}>
      <header><div><h2 id="price-notice-title">New WiFi prices</h2><p>Effective 10 October 2026</p></div><button autoFocus type="button" aria-label="Close price notice" onClick={() => setOpen(false)}>Close</button></header>
      <a href={prices} target="_blank" rel="noreferrer"><img src={prices} alt="New WiFi price list effective 10 October 2026. Open the image to zoom in." /></a>
      <p><a href={prices} target="_blank" rel="noreferrer">Open full-size price list</a></p>
    </dialog>
  </>
}
