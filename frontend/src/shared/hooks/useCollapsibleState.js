import { useState, useCallback } from 'react'

/**
 * Hook that persists collapsible open/closed state in localStorage.
 * @param {string} pageKey - Identifies the page (e.g., "employer", "union")
 * @param {string} sectionId - Identifies the section (e.g., "osha", "nlrb")
 * @param {boolean} defaultOpen - Default state if no saved preference
 * @returns {[boolean, Function]} - [isOpen, toggle]
 */
export function useCollapsibleState(pageKey, sectionId, defaultOpen = false) {
  const storageKey = `collapse:${pageKey}:${sectionId}`
  const [isOpen, setIsOpen] = useState(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      return saved !== null ? saved === 'true' : defaultOpen
    } catch {
      return defaultOpen
    }
  })

  const toggle = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev
      try {
        localStorage.setItem(storageKey, String(next))
      } catch {}
      return next
    })
  }, [storageKey])

  return [isOpen, toggle]
}
