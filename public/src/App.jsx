import AccountPage from './pages/AccountPage'
import LoginPage from './pages/LoginPage'
import ProfilePage from './pages/ProfilePage'
import SignupPage from './pages/SignupPage'

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '')
  if (path === '/signup') return <SignupPage />
  if (path === '/account') return <AccountPage />
  if (path === '/profile') return <ProfilePage />
  return <LoginPage />
}
