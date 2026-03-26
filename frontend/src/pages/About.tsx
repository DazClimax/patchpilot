import React from 'react'
import { colors, glowText, glassBg } from '../theme'
import { Card } from '../components/Card'
import { PageHeader } from '../components/SectionHeader'

export function AboutPage() {
  const linkStyle: React.CSSProperties = {
    color: colors.primary,
    textDecoration: 'none',
    textShadow: glowText(colors.primary, 3),
  }

  return (
    <div style={{ padding: 'clamp(16px, 4vw, 32px)', maxWidth: '1400px', animation: 'pp-fadein 0.4s ease both' }}>
      <PageHeader>About</PageHeader>

      <Card style={{ padding: '28px 32px' }}>
        <div style={{
          fontFamily: "'Orbitron', sans-serif",
          fontSize: '24px',
          letterSpacing: '0.15em',
          color: colors.primary,
          textShadow: glowText(colors.primary, 6),
          marginBottom: '6px',
        }}>
          PATCHPILOT
        </div>
        <div style={{
          fontSize: '12px',
          color: colors.textMuted,
          fontFamily: "'Electrolize', monospace",
          letterSpacing: '0.1em',
          marginBottom: '28px',
        }}>
          Self-hosted patch management for Linux VMs
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <Row label="CODER" value={<span style={{ color: colors.text }}>DazClimax</span>} />
          <Row label="GITHUB" value={
            <a href="https://github.com/DazClimax/patchpilot" target="_blank" rel="noopener noreferrer" style={linkStyle}>
              github.com/DazClimax/patchpilot
            </a>
          } />
          <Row label="LICENSE" value={
            <span style={{ color: colors.text }}>
              GNU General Public License v3.0 (GPLv3)
            </span>
          } />
        </div>

        <div style={{
          marginTop: '28px',
          padding: '16px 20px',
          background: glassBg(0.5),
          border: `1px solid ${colors.border}`,
          fontSize: '11px',
          color: colors.textDim,
          fontFamily: 'monospace',
          lineHeight: 1.7,
        }}>
          This program is free software: you can redistribute it and/or modify
          it under the terms of the GNU General Public License as published by
          the Free Software Foundation, either version 3 of the License, or
          (at your option) any later version.
          <br /><br />
          This program is distributed in the hope that it will be useful,
          but WITHOUT ANY WARRANTY; without even the implied warranty of
          MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the{' '}
          <a href="https://www.gnu.org/licenses/gpl-3.0.html" target="_blank" rel="noopener noreferrer" style={linkStyle}>
            GNU General Public License
          </a>{' '}
          for more details.
        </div>
      </Card>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px' }}>
      <span style={{
        fontSize: '10px',
        letterSpacing: '0.2em',
        color: colors.textMuted,
        fontFamily: "'Orbitron', sans-serif",
        minWidth: '70px',
        flexShrink: 0,
      }}>
        {label}
      </span>
      <span style={{ fontSize: '12px', fontFamily: "'Electrolize', monospace" }}>
        {value}
      </span>
    </div>
  )
}
