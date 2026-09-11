import { useEffect } from 'react'

import { WifiIcon } from '../components/Icons'

const EFFECTIVE_DATE = '11 September 2026'

function Terms() {
  return (
    <>
      <h1>Terms and Conditions</h1>
      <p className="legal-lead">These terms govern your Vlad WiFi account and use of Vlad-managed hotspot services.</p>

      <h2>1. Who provides the service</h2>
      <p>Vlad WiFi (“Vlad WiFi”, “we”, “us”) provides prepaid WiFi access through participating hostels and network operators. The hostel selected during signup determines the network on which your account may be used.</p>

      <h2>2. Your account</h2>
      <p>You must provide an accurate email address and mobile phone number, keep your six-digit PIN private, and tell support promptly if you believe someone has accessed your account. We verify your mobile number by sending a one-time code through SMS. You may not transfer, sell, share, or misuse an account. You must be at least 18 years old, or have permission from a parent or legal guardian.</p>

      <h2>3. Plans, activation, and replacement</h2>
      <p>Plan price, data, speed, device allowance, duration, and promotional restrictions are shown before checkout. A duration-based plan begins when you first sign in through the captive portal, unless the plan description says otherwise. Buying another plan while one is active replaces the current plan, removes unused access under it, clears usage counters, and signs out connected devices and remembered hotspot cookies. You must sign in again. A one-use promotional plan may only be purchased once per account.</p>

      <h2>4. Payments and refunds</h2>
      <p>Payments are processed by Paystack. A plan is issued only after payment is verified. Charges are shown in the stated currency before payment. If you are charged but a plan is not activated, use Vlad WiFi support so the transaction can be reconciled. Refunds are considered where required by law or where Vlad WiFi cannot provide the paid service; misuse, consumed data, or a voluntary plan replacement may limit refund eligibility.</p>

      <h2>5. Service communications</h2>
      <p>We may use your registered phone number and email address to send one-time verification codes, bundle activation confirmations, security alerts, service interruptions, account notices, and other messages reasonably necessary to operate your Vlad WiFi account. Your mobile provider may apply its normal SMS charges. Promotional or direct-marketing messages will be sent only where permitted by law and where any required permission has been obtained.</p>

      <h2>6. Acceptable use</h2>
      <p>Do not use the service for unlawful activity, harassment, fraud, infringement, attacks, malware, unauthorized access, excessive interference with other users, or resale. We may suspend or close an account where reasonably necessary to protect users, the network, comply with law, investigate abuse, or enforce these terms.</p>

      <h2>7. Availability and fair limits</h2>
      <p>Internet speeds stated for a plan describe the maximum speed configured for that plan. Actual speeds may vary because of network congestion, the number of users sharing the network, your device, interference, and your distance from the WiFi access point.</p>
      <p>The WiFi system and its supporting equipment require electricity to operate. Power outages at a hostel, access point, router location, or other supporting facility may cause the service to slow down, disconnect, or become completely unavailable until power is restored. Maintenance, upstream-provider failures, equipment faults, and other events outside our reasonable control may also interrupt service. We will use reasonable care to operate the service but cannot promise uninterrupted availability.</p>

      <h2>8. Account closure</h2>
      <p>You can permanently delete your account from Profile after confirming your PIN. Accounts with no Vlad WiFi account activity for 365 days are automatically deleted once no active or pending paid plan remains. Deletion removes the Vlad WiFi account and MikroTik hotspot identity, subject to records that must be retained by law or remain with independent payment and infrastructure providers under their own legal duties.</p>

      <h2>9. Liability and changes</h2>
      <p>Nothing in these terms excludes rights or liabilities that Ghanaian law does not allow us to exclude. To the extent permitted by law, Vlad WiFi is not responsible for indirect losses or content and services supplied by third parties. We may update these terms for legal, security, or service changes and will present material new terms for acceptance where required.</p>

      <h2>10. Law and support</h2>
      <p>These terms are governed by the laws of Ghana. Contact Vlad WiFi support through the support channel shown on the service if you have a billing, privacy, or account complaint.</p>
    </>
  )
}

function Privacy() {
  return (
    <>
      <h1>Privacy Notice</h1>
      <p className="legal-lead">This notice explains how Vlad WiFi handles personal data when you create an account, purchase a plan, and use the hotspot.</p>

      <h2>1. Data controller and data we collect</h2>
      <p>Vlad WiFi is the controller of account data used to provide this service. We collect your email address, mobile phone number, username, selected hostel, securely hashed PIN, phone and email verification records, account activity and session details, plan and payment references, hotspot usage and connected-device information, IP address, MAC address where supplied by the hotspot, and technical support, notification-delivery, or security records.</p>

      <h2>2. Why we use it</h2>
      <p>We use data to create and secure accounts, verify phone numbers, authenticate users, process and reconcile payments, activate MikroTik plans, confirm bundle activation, send security, account, and operational service notices, communicate with all customers or customers at a selected hostel, display usage and devices, enforce one-use promotions, prevent fraud and abuse, provide support, maintain the service, comply with law, and establish or defend legal claims. We process information needed to perform our service contract, meet legal obligations, protect legitimate security and service interests, and obtain consent where the law requires it.</p>

      <h2>3. Providers and transfers</h2>
      <p>Necessary data may be handled by Paystack for payments, mNotify for SMS verification and notifications, Brevo for transactional and service email, MikroTik routers for network access, and our database, hosting, security, and connectivity providers. mNotify receives the destination phone number and SMS content; Brevo receives the destination email address, subject, and email content. Some providers may process data outside Ghana. We require appropriate protection and share only what is needed for their role. Their independent services may also be governed by their own privacy notices.</p>

      <h2>4. Cookies</h2>
      <p>We use essential, secure session cookies for account and hotspot functions. If you select “Remember me”, your account session cookie remains on that device for up to 30 days; otherwise it is a browser-session cookie. You can remove it by logging out or clearing browser data. We do not use this choice as consent for advertising cookies.</p>

      <h2>5. Retention and deletion</h2>
      <p>Account activity is refreshed when you sign in or use authenticated Vlad WiFi account features. We automatically delete an account after 365 days with no such activity once it has no active or pending plan. You can delete it sooner from Profile. Account deletion removes associated local sessions, verification challenges, subscriptions, activation history, payment-event copies, and the MikroTik user. Limited payment, security, audit, and message-delivery records may be retained where law requires it, a dispute or fraud investigation is active, or an independent provider such as Paystack, mNotify, or Brevo must keep its own records.</p>

      <h2>6. Security</h2>
      <p>PINs, one-time codes, and session tokens are stored as one-way hashes rather than plaintext. Phone numbers and email addresses are available only to authorized systems and administrators who need them for account operations and communications. We apply access controls and reasonable technical and organizational safeguards. No internet service can guarantee absolute security, so contact support promptly if you suspect compromise.</p>

      <h2>7. Your rights</h2>
      <p>Subject to Ghanaian law, you may ask to be informed about processing, access your data, correct an inaccurate phone number, email address, or other information, object to or restrict certain processing, withdraw consent where consent is the basis, and request deletion. You may also complain to Ghana&apos;s Data Protection Commission. Vlad WiFi does not sell personal data and will not send direct marketing without the permission required by law.</p>

      <h2>8. Changes and contact</h2>
      <p>We may update this notice when the service or law changes. The current version and effective date will remain available here. Send privacy and rights requests through the Vlad WiFi support channel shown on the service.</p>
    </>
  )
}

export default function LegalPage({ legalDocument }) {
  const isPrivacy = legalDocument === 'privacy'

  useEffect(() => {
    document.title = `${isPrivacy ? 'Privacy Notice' : 'Terms and Conditions'} | Vlad WiFi`
  }, [isPrivacy])

  return (
    <main className="signup-page legal-page">
      <div className="legal-shell">
        <header className="legal-header">
          <a className="signup-brand" href="/" aria-label="Vlad WiFi home">
            <span className="signup-logo-mark"><WifiIcon /></span>
            <span>Vlad WiFi</span>
          </a>
          <nav aria-label="Legal documents">
            <a className={!isPrivacy ? 'active' : ''} href="/terms">Terms</a>
            <a className={isPrivacy ? 'active' : ''} href="/privacy">Privacy</a>
          </nav>
        </header>
        <article className="legal-card">
          {isPrivacy ? <Privacy /> : <Terms />}
          <p className="legal-effective">Effective: {EFFECTIVE_DATE}</p>
        </article>
        <a className="legal-back" href="/signup">Back to signup</a>
      </div>
    </main>
  )
}
