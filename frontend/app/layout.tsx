import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'AI Story Video Generator',
  description: 'Turn your ideas into narrated story videos with AI',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-white/10">
          <div className="container py-5 flex items-center justify-between">
            <h1 className="text-xl font-semibold">AI Story Video Generator</h1>
            <nav className="flex items-center gap-4 text-sm text-white/70">
              <a href="/" className="hover:text-white">Generate</a>
              <a href="/sessions" className="hover:text-white">Sessions</a>
              <a href="https://github.com/" target="_blank" className="hover:text-white">Docs</a>
            </nav>
          </div>
        </header>
        <main className="container py-8">
          {children}
        </main>
        <footer className="container py-10 text-center text-sm text-white/50">
          Built with Next.js + FastAPI
        </footer>
      </body>
    </html>
  )
}
