import { useEffect, useRef } from 'react'

const OTP_LENGTH = 6

export default function OtpInput({ id, value, onChange, invalid = false, autoFocus = false }) {
  const inputs = useRef([])
  const digits = Array.from({ length: OTP_LENGTH }, (_, index) => value[index] || '')

  useEffect(() => {
    if (autoFocus) inputs.current[0]?.focus()
  }, [autoFocus])

  function setDigits(nextDigits, focusIndex) {
    onChange(nextDigits.join('').replace(/\D/g, '').slice(0, OTP_LENGTH))
    if (focusIndex !== undefined) {
      window.requestAnimationFrame(() => inputs.current[focusIndex]?.focus())
    }
  }

  function input(index, rawValue) {
    const entered = rawValue.replace(/\D/g, '')
    if (entered.length > 1) {
      const next = [...digits]
      entered.slice(0, OTP_LENGTH - index).split('').forEach((digit, offset) => {
        next[index + offset] = digit
      })
      setDigits(next, Math.min(index + entered.length, OTP_LENGTH - 1))
      return
    }
    const next = [...digits]
    next[index] = entered
    setDigits(next, entered && index < OTP_LENGTH - 1 ? index + 1 : index)
  }

  function keyDown(index, event) {
    if (event.key === 'Backspace') {
      event.preventDefault()
      const next = [...digits]
      if (next[index]) next[index] = ''
      else if (index > 0) next[index - 1] = ''
      setDigits(next, next[index] || index === 0 ? index : index - 1)
    } else if (event.key === 'ArrowLeft' && index > 0) {
      event.preventDefault(); inputs.current[index - 1]?.focus()
    } else if (event.key === 'ArrowRight' && index < OTP_LENGTH - 1) {
      event.preventDefault(); inputs.current[index + 1]?.focus()
    }
  }

  function paste(event) {
    const pasted = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, OTP_LENGTH)
    if (!pasted) return
    event.preventDefault()
    const next = Array(OTP_LENGTH).fill('')
    pasted.split('').forEach((digit, index) => { next[index] = digit })
    setDigits(next, Math.min(pasted.length, OTP_LENGTH - 1))
  }

  return (
    <div className={`otp-boxes${invalid ? ' invalid' : ''}`} role="group" aria-label="Six-digit verification code" onPaste={paste}>
      {digits.map((digit, index) => (
        <input
          aria-label={`Digit ${index + 1}`}
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          className="otp-box"
          inputMode="numeric"
          id={index === 0 ? id : undefined}
          key={index}
          maxLength={index === 0 ? 6 : 1}
          ref={(element) => { inputs.current[index] = element }}
          type="text"
          value={digit}
          onChange={(event) => input(index, event.target.value)}
          onFocus={(event) => event.target.select()}
          onKeyDown={(event) => keyDown(index, event)}
        />
      ))}
    </div>
  )
}
