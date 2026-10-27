import { useCallback, useEffect, useState } from 'react'
import { getReviewConfig, listAssets, resetDemo } from './api'
import type { AssetSummary, ReviewConfig } from './api'
import { Insights } from './pages/Insights'
import { NewCheck } from './pages/NewCheck'
import { Queue } from './pages/Queue'
import { Review } from './pages/Review'
import { Rules } from './pages/Rules'
import { href, useRoute } from './router'

function App() {
  const route = useRoute()
  const [assets, setAssets] = useState<AssetSummary[] | null>(null)
  const [config, setConfig] = useState<ReviewConfig | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [resetting, setResetting] = useState(false)

  const refresh = useCallback(() => {
    listAssets().then(setAssets).catch(() => setAssets([]))
  }, [])

  useEffect(refresh, [refresh, route])
  useEffect(() => {
    getReviewConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  async function reset() {
    setResetting(true)
    try {
      await resetDemo()
      window.location.hash = href.queue
      refresh()
    } finally {
      setResetting(false)
      setConfirmReset(false)
    }
  }

  const inReview = assets?.filter((a) => a.status === 'in_review').length ?? 0
  const initials = (config?.actor ?? 'Reviewer')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <>
      <header className="topbar">
        <a className="brand" href={href.queue}>
          <span className="logo">CP</span>
          <span className="name">
            ClearPath <b>Compliance</b>
          </span>
        </a>
        <nav>
          <a className={route.page === 'queue' || route.page === 'review' ? 'on' : ''} href={href.queue}>
            Queue {inReview > 0 && <span className="count">{inReview}</span>}
          </a>
          <a className={route.page === 'new' ? 'on' : ''} href={href.new}>
            New check
          </a>
          <a className={route.page === 'rules' ? 'on' : ''} href={href.rules}>
            Rules
          </a>
          <a className={route.page === 'insights' ? 'on' : ''} href={href.insights}>
            Insights
          </a>
        </nav>
        <div className="who">
          {confirmReset ? (
            <span className="reset-confirm">
              Reset the demo queue for everyone?
              <button className="btn small danger" disabled={resetting} onClick={reset}>
                {resetting ? 'Resetting…' : 'Reset'}
              </button>
              <button className="btn small" disabled={resetting} onClick={() => setConfirmReset(false)}>
                Cancel
              </button>
            </span>
          ) : (
            <button className="btn small ghost" onClick={() => setConfirmReset(true)}>
              Reset demo
            </button>
          )}
          <span className="avatar">{initials}</span>
          <span>
            {config?.actor ?? 'Reviewer'} <small>Reviewer</small>
          </span>
        </div>
      </header>

      <main className="page">
        {route.page === 'queue' && <Queue key={route.rule ?? ''} assets={assets} rule={route.rule} />}
        {route.page === 'review' && config && <Review key={route.id} id={route.id} config={config} onChange={refresh} />}
        {route.page === 'new' && <NewCheck />}
        {route.page === 'rules' && <Rules config={config} focus={route.focus} />}
        {route.page === 'insights' && <Insights config={config} />}
      </main>
    </>
  )
}

export default App
