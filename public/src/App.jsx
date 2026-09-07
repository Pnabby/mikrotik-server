import AccountPage from './pages/AccountPage'
import LoginPage from './pages/LoginPage'
import ForgotPinPage from './pages/ForgotPinPage'
import ProfilePage from './pages/ProfilePage'
import SignupPage from './pages/SignupPage'
import LegalPage from './pages/LegalPage'
import SupportContact from './components/SupportContact'

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '')
  let page = <LoginPage />
  if (path === '/signup') page = <SignupPage />
  else if (path === '/forgot-password') page = <ForgotPinPage />
  else if (path === '/account') page = <AccountPage />
  else if (path === '/profile') page = <ProfilePage />
  else if (path === '/terms') page = <LegalPage legalDocument="terms" />
  else if (path === '/privacy') page = <LegalPage legalDocument="privacy" />
  return <>{page}<SupportContact /></>
}
