import { useCallback, useEffect, useRef, useState } from 'react'

import {
  getHotspotStatus,
  getStatusSession,
  lookupHotspotUser,
  logoutHotspotDevice,
} from '../services/hotspotApi'
import { normalizeText, publicErrorMessage } from '../utils/formatters'


const EMPTY_ACTIVE = {
  username: '',
  routerId: '',
  routerName: '',
  password: '',
  isLookupResult: false,
}

export function useHotspotStatus() {
  const [session, setSession] = useState(null)
  const [active, setActive] = useState(EMPTY_ACTIVE)
  const [payload, setPayload] = useState(null)
  const [phase, setPhase] = useState('bootstrapping')
  const [errorMessage, setErrorMessage] = useState('')
  const [lookupOpen, setLookupOpen] = useState(false)
  const [lookupError, setLookupError] = useState('')
  const [logoutTarget, setLogoutTarget] = useState(null)
  const [logoutError, setLogoutError] = useState('')
  const [logoutLoading, setLogoutLoading] = useState(false)
  const [longLoading, setLongLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const activeRef = useRef(EMPTY_ACTIVE)
  const loadingRef = useRef(false)

  const updateActive = useCallback((next) => {
    activeRef.current = next
    setActive(next)
  }, [])

  const loadStatus = useCallback(
    async (username, password = '', routerId, routerName = '') => {
      const normalizedUsername = normalizeText(username)
      const normalizedRouterId = normalizeText(routerId)
      if (!normalizedUsername || !normalizedRouterId || loadingRef.current) return false

      const isLookupResult = Boolean(password)
      const nextActive = {
        username: normalizedUsername,
        routerId: normalizedRouterId,
        routerName: normalizeText(routerName) || activeRef.current.routerName,
        password,
        isLookupResult,
      }
      updateActive(nextActive)
      loadingRef.current = true
      setPhase('loading')
      setLookupError('')
      setErrorMessage('')

      try {
        const result = isLookupResult
          ? await lookupHotspotUser(normalizedRouterId, normalizedUsername, password)
          : await getHotspotStatus(normalizedRouterId, normalizedUsername)
        const resolvedActive = {
          ...nextActive,
          username: normalizeText(result.username) || normalizedUsername,
          routerId: normalizeText(result.router_id) || normalizedRouterId,
          routerName:
            normalizeText(result.router_name) || nextActive.routerName || normalizedRouterId,
        }
        updateActive(resolvedActive)
        setPayload(result)
        setLastUpdated(new Date())
        setPhase('loaded')
        if (isLookupResult) setLookupOpen(false)
        return true
      } catch (error) {
        const fallback = isLookupResult
          ? 'Could not verify this voucher.'
          : 'Could not load voucher details.'
        const message = error?.status ? publicErrorMessage(error.status) : fallback
        setErrorMessage(message)
        setPhase('error')
        if (isLookupResult) setLookupError(message)
        return false
      } finally {
        loadingRef.current = false
      }
    },
    [updateActive],
  )

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        const result = await getStatusSession(window.location.search)
        if (cancelled) return
        setSession(result)
        const selected = result.selected_router
        const initialActive = {
          ...EMPTY_ACTIVE,
          username: normalizeText(result.username),
          routerId: selected.router_id,
          routerName: selected.name,
        }
        updateActive(initialActive)
        if (initialActive.username) {
          await loadStatus(
            initialActive.username,
            '',
            initialActive.routerId,
            initialActive.routerName,
          )
        } else {
          setPhase('idle')
        }
      } catch (error) {
        if (cancelled) return
        setErrorMessage(publicErrorMessage(error?.status))
        setPhase('error')
      }
    }
    bootstrap()
    return () => {
      cancelled = true
    }
  }, [loadStatus, updateActive])

  useEffect(() => {
    if (phase !== 'loading') {
      setLongLoading(false)
      return undefined
    }
    const timer = window.setTimeout(() => setLongLoading(true), 6000)
    return () => window.clearTimeout(timer)
  }, [phase])

  useEffect(() => {
    document.body.classList.toggle('modal-open', lookupOpen || Boolean(logoutTarget))
    return () => document.body.classList.remove('modal-open')
  }, [lookupOpen, logoutTarget])

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key !== 'Escape') return
      if (lookupOpen && phase !== 'loading') setLookupOpen(false)
      else if (logoutTarget && !logoutLoading) setLogoutTarget(null)
    }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [lookupOpen, logoutLoading, logoutTarget, phase])

  const openLookup = useCallback(() => {
    setLookupError('')
    setLookupOpen(true)
  }, [])

  const closeLookup = useCallback(() => {
    if (phase === 'loading') return
    setLookupError('')
    setLookupOpen(false)
  }, [phase])

  const lookup = useCallback(
    (username, password, routerId) => {
      const router = session?.routers.find((item) => item.router_id === routerId)
      return loadStatus(username, password, routerId, router?.name)
    },
    [loadStatus, session],
  )

  const refresh = useCallback(() => {
    const current = activeRef.current
    return loadStatus(
      current.username,
      current.password,
      current.routerId,
      current.routerName,
    )
  }, [loadStatus])

  const requestLogout = useCallback((device) => {
    setLogoutError('')
    setLogoutTarget(device)
  }, [])

  const closeLogout = useCallback(() => {
    if (logoutLoading) return
    setLogoutError('')
    setLogoutTarget(null)
  }, [logoutLoading])

  const confirmLogout = useCallback(async () => {
    if (!logoutTarget || logoutLoading) return
    const current = activeRef.current
    setLogoutLoading(true)
    setLogoutError('')
    try {
      await logoutHotspotDevice(current.routerId, current.username, logoutTarget)
      setLogoutTarget(null)
      await loadStatus(
        current.username,
        current.password,
        current.routerId,
        current.routerName,
      )
    } catch (error) {
      setLogoutError(publicErrorMessage(error?.status))
    } finally {
      setLogoutLoading(false)
    }
  }, [loadStatus, logoutLoading, logoutTarget])

  return {
    active,
    closeLogout,
    closeLookup,
    confirmLogout,
    errorMessage,
    lastUpdated,
    loadStatus,
    longLoading,
    logoutError,
    logoutLoading,
    logoutTarget,
    lookup,
    lookupError,
    lookupOpen,
    openLookup,
    payload,
    phase,
    refresh,
    requestLogout,
    session,
  }
}
