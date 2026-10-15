/* Global "a test is running" flag. While any page holds a lock, selected words can
   only be saved (their meaning stays hidden) and the AI tutor is unavailable. */
import { useEffect, useSyncExternalStore } from 'react'

const locks = new Set<string>()
const listeners = new Set<() => void>()
const emit = () => listeners.forEach(listener => listener())

export const isExamLocked = () => locks.size > 0

export function useExamLock(id: string, active: boolean) {
  useEffect(() => {
    if (active) locks.add(id)
    else locks.delete(id)
    emit()
    return () => { locks.delete(id); emit() }
  }, [id, active])
}

export function useIsExamLocked() {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener) } }, isExamLocked)
}
