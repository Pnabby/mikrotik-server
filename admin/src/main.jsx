import { createRoot } from 'react-dom/client'

import App from './App'
import { applyTheme, initialTheme } from './theme'
import './theme.css'
import './styles.css'
import './colors.css'
import './header.css'

applyTheme(initialTheme())
createRoot(document.getElementById('root')).render(<App />)
