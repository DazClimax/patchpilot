// PatchPilot design tokens — Arwes sci-fi palette
export const colors = {
  bg:         '#020c0e',
  bgCard:     '#040f12',
  bgCardGlass:'#071419',
  bgHover:    '#0a1e24',
  border:     '#0d3540',
  borderGlow: '#27e1fa',
  primary:    '#27e1fa',
  primaryDim: '#1aabb8',
  secondary:  '#fae127',
  danger:     '#fa4227',
  success:    '#27fa6e',
  warn:       '#fa9c27',
  text:       '#c7e8ec',
  textDim:    '#5d8a92',
  textMuted:  '#2a5560',
}

// Standard glow — subtle ambient
export const glow = (color: string, size = 8) =>
  `0 0 ${size}px ${color}44, 0 0 ${size * 2}px ${color}22`

// Strong glow — for active/hover elements
export const glowStrong = (color: string) =>
  `0 0 6px ${color}, 0 0 20px ${color}66, 0 0 40px ${color}22`

// Text glow
export const glowText = (color: string, size = 8) =>
  `0 0 ${size}px ${color}88`

// Glassmorphism card background
export const glassBg = (opacity = 0.55) =>
  `rgba(4, 15, 18, ${opacity})`

// Inset border glow for focused inputs / active cards
export const glowInset = (color: string) =>
  `inset 0 0 12px ${color}18, 0 0 0 1px ${color}44`

// CSS for scrollbar theming (inject as <style> where needed)
export const scrollbarCSS = `
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: #010a0c; }
  ::-webkit-scrollbar-thumb { background: #0d3540; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #27e1fa44; }
`

// Global keyframe definitions (inject once in Layout)
export const globalKeyframes = `
  @keyframes pp-pulse       { 0%,100%{opacity:1}       50%{opacity:0.35} }
  @keyframes pp-blink       { 0%,100%{opacity:1}       49%{opacity:1} 50%{opacity:0} }
  @keyframes pp-scan        { 0%{transform:translateY(-100%)} 100%{transform:translateY(100vh)} }
  @keyframes pp-fadein      { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
  @keyframes pp-slideright  { from{opacity:0;transform:translateX(-12px)} to{opacity:1;transform:translateX(0)} }
  @keyframes pp-shimmer     { 0%{background-position:-400px 0} 100%{background-position:400px 0} }
  @keyframes pp-glow-border { 0%,100%{border-color:#0d3540} 50%{border-color:#27e1fa44} }
  @keyframes pp-spin        { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
  @keyframes pp-warn-pulse  { 0%,100%{box-shadow:0 0 8px #fa422744} 50%{box-shadow:0 0 20px #fa422788, 0 0 40px #fa422722} }
`
