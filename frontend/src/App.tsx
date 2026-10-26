import { useEffect, useState } from 'react'

type Health = { api: string; db: string }

// Placeholder screen for the deploy shell: proves browser -> API -> database works.
function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then(setHealth)
      .catch((err) => setError(String(err)))
  }, [])

  return (
    <main style={{ maxWidth: 640, margin: '64px auto', padding: '0 16px' }}>
      <h1>ClearPath Compliance Review</h1>
      {error && <p>API unreachable: {error}</p>}
      {!health && !error && <p>Checking…</p>}
      {health && (
        <ul>
          <li>API: {health.api}</li>
          <li>Database: {health.db}</li>
        </ul>
      )}
    </main>
  )
}

export default App
