import { BrowserRouter, Routes, Route } from 'react-router-dom'

function HomePage() {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--color-neutral-50)' }}>
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold" style={{ color: 'var(--color-primary)' }}>
          EkamCore
        </h1>
        <p className="text-lg" style={{ color: 'var(--color-neutral-600)' }}>
          Your private, local-first life assistant
        </p>
        <div className="pt-4">
          <span
            className="inline-block px-3 py-1 rounded-full text-sm font-medium"
            style={{
              backgroundColor: 'var(--color-neutral-200)',
              color: 'var(--color-neutral-700)',
            }}
          >
            Phase 0 — Scaffold
          </span>
        </div>
      </div>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="*" element={<div className="p-8 text-center">404 — Not Found</div>} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
