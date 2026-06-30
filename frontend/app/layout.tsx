import './globals.css'
import React from 'react'

export const metadata = {
  title: 'Interlace — Research Adjacency Engine',
  description: 'Discover what is adjacent to any research idea. Map frontier adjacency pathways, feasibility scores, and causal citation chains instantly.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" style={{ overflow: 'hidden', height: '100%' }}>
      <body style={{ overflow: 'hidden', height: '100%', margin: 0, padding: 0 }}>{children}</body>
    </html>
  )
}
