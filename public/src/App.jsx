import AccountHeader from './components/AccountHeader'
import SiteFooter from './components/SiteFooter'
import AccountPage from './pages/AccountPage'
import LoginPage from './pages/LoginPage'
import ForgotPinPage from './pages/ForgotPinPage'
import ProfilePage from './pages/ProfilePage'
import SignupPage from './pages/SignupPage'
import LegalPage from './pages/LegalPage'
import SupportContact from './components/SupportContact'
import VerifyPhonePage from './pages/VerifyPhonePage'
import IssuesPage from './pages/IssuesPage'

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '')
  let page = <LoginPage />
  if (path === '/signup') page = <SignupPage />
  else if (path === '/forgot-password') page = <ForgotPinPage />
  else if (path === '/unlock-account') page = <ForgotPinPage unlockAccount />
  else if (path === '/account') page = <AccountPage />
  else if (path === '/plans') page = <AccountPage plansOnly />
  else if (/^\/plans\/[^/]+$/.test(path)) page = <AccountPage plansOnly planGroupId={path.slice('/plans/'.length)} />
  else if (path === '/profile') page = <ProfilePage />
  else if (path === '/issues') page = <IssuesPage />
  else if (path === '/verify-phone') page = <VerifyPhonePage />
  else if (path === '/terms') page = <LegalPage legalDocument="terms" />
  else if (path === '/privacy') page = <LegalPage legalDocument="privacy" />
  const pageHasHeader = path === '/account' || path === '/profile' || path === '/issues' || path === '/plans' || path.startsWith('/plans/')
  const isLoginPage = page.type === LoginPage
  const isRecoveryPage = page.type === ForgotPinPage
  return <div className={`customer-site${isLoginPage ? ' login-site' : ''}${isRecoveryPage ? ' recovery-site' : ''}`}>{!pageHasHeader && !isLoginPage && !isRecoveryPage && <AccountHeader activePage="guest" />}{page}{!isLoginPage && !isRecoveryPage && <SiteFooter />}<SupportContact /></div>
}
