import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { BleepsProvider } from '@arwes/react'

type UiEffectsSettings = {
  audioEnabled: boolean
  audioVolume: number
  loginAnimationEnabled: boolean
}

const STORAGE_KEYS = {
  enabled: 'pp_ui_audio_enabled',
  volume: 'pp_ui_audio_volume',
  loginAnimation: 'pp_ui_login_animation_enabled',
}

const DEFAULT_SETTINGS: UiEffectsSettings = {
  audioEnabled: true,
  audioVolume: 70,
  loginAnimationEnabled: true,
}

export const UI_EFFECTS_EVENT = 'pp-effects-changed'

function clampVolume(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_SETTINGS.audioVolume
  return Math.max(0, Math.min(100, Math.round(value)))
}

function readUiEffectsSettings(): UiEffectsSettings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS
  const enabled = window.localStorage.getItem(STORAGE_KEYS.enabled)
  const volume = window.localStorage.getItem(STORAGE_KEYS.volume)
  const loginAnimation = window.localStorage.getItem(STORAGE_KEYS.loginAnimation)
  return {
    audioEnabled: enabled == null ? DEFAULT_SETTINGS.audioEnabled : enabled === '1',
    audioVolume: clampVolume(volume == null ? DEFAULT_SETTINGS.audioVolume : Number(volume)),
    loginAnimationEnabled: loginAnimation == null ? DEFAULT_SETTINGS.loginAnimationEnabled : loginAnimation === '1',
  }
}

export function persistUiEffectsSettings(next: UiEffectsSettings) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEYS.enabled, next.audioEnabled ? '1' : '0')
  window.localStorage.setItem(STORAGE_KEYS.volume, String(clampVolume(next.audioVolume)))
  window.localStorage.setItem(STORAGE_KEYS.loginAnimation, next.loginAnimationEnabled ? '1' : '0')
  window.dispatchEvent(new CustomEvent(UI_EFFECTS_EVENT))
}

const UiEffectsContext = createContext<UiEffectsSettings>(DEFAULT_SETTINGS)

export function useUiEffects() {
  return useContext(UiEffectsContext)
}

export function UiEffectsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<UiEffectsSettings>(() => readUiEffectsSettings())

  useEffect(() => {
    const sync = () => setSettings(readUiEffectsSettings())
    window.addEventListener('storage', sync)
    window.addEventListener(UI_EFFECTS_EVENT, sync as EventListener)
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener(UI_EFFECTS_EVENT, sync as EventListener)
    }
  }, [])

  const bleepsSettings = useMemo(() => ({
    master: {
      volume: settings.audioVolume / 100,
    },
    common: {
      muted: !settings.audioEnabled,
      preload: true,
      muteOnWindowBlur: true,
    },
    bleeps: {
      click: {
        category: 'interaction' as const,
        sources: [{ src: '/sounds/arwes-click.mp3', type: 'audio/mpeg' }],
      },
    },
  }), [settings.audioEnabled, settings.audioVolume])

  return (
    <UiEffectsContext.Provider value={settings}>
      <BleepsProvider {...bleepsSettings}>
        {children}
      </BleepsProvider>
    </UiEffectsContext.Provider>
  )
}
