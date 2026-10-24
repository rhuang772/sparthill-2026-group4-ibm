import { useEffect, useState } from 'react';
import AppShell from '../components/AppShell';
import { deleteBriefing, listBriefings } from '../services/offlineStorage';
import type { SavedBriefing } from '../services/offlineStorage';
import { useAppContext } from '../context/AppContext';
import { offlineStatus } from '../services/freshness';
import { downloadBriefingPdf } from '../services/briefingPdf';

export default function SavedBriefingsPage() {
  const [items, setItems] = useState<SavedBriefing[]>([]);
  const [status, setStatus] = useState('');
  const { resetPrivateData } = useAppContext();
  async function refresh() { setItems(await listBriefings()); }
  useEffect(() => { void refresh().catch(() => setStatus('Cannot read local storage.')); }, []);
  async function remove(id: string) {
    await deleteBriefing(id); await refresh(); setStatus('Saved briefing deleted.');
  }
  async function eraseAll() {
    if (!window.confirm('Delete all SkyBrief profiles, flight plans, and saved briefings on this device?')) return;
    await resetPrivateData(); await refresh(); setStatus('All locally saved SkyBrief information deleted.');
  }
  return <AppShell currentStep={3}><div style={{maxWidth:800,margin:'2rem auto',padding:'0 1rem'}}>
    <h1>Saved Briefings</h1>
    <p>These are stored in this browser on this device. They are advisory only. Browser storage may be cleared by your browser or device.</p>
    <p>Offline: previously opened app screens may work without internet; map tiles, weather updates, FAA updates and the cloud AI need a connection.</p>
    <p role="status">{status}</p>
    {items.length === 0 ? <p>No saved briefings yet.</p> : items.map(item => <article key={item.id} style={{border:'1px solid #999',borderRadius:10,padding:16,margin:'12px 0'}}>
      <h2>{item.flightPlan?.location.displayName ?? item.briefing.locationLabel}</h2>
      <p>Saved: {new Date(item.savedAt).toLocaleString()}</p>
      <p>Planned: {item.flightPlan ? `${item.flightPlan.date} ${item.flightPlan.time}` : item.briefing.dateTimeLabel}</p>
      <p><strong>{item.demo ? 'DEMO / MOCK DATA' : 'Saved briefing'}</strong></p>
      <p><strong>Offline status: {offlineStatus(item.sources?.weather?.fetchedAt, item.sources?.faa?.fetchedAt) === 'caution' ? 'CAUTION — data unavailable or stale' : 'Unverified'}</strong></p>
      <p>Original (not revalidated) verdict: {item.briefing.verdict.result.toUpperCase()}. Not current authorization.</p>
      <div
  style={{
    display: 'flex',
    gap: 10,
    flexWrap: 'wrap',
    alignItems: 'center',
    marginBottom: 16,
  }}
>
  <button
    onClick={() => {
      try {
        downloadBriefingPdf(item);
        setStatus('PDF download started.');
      } catch {
        setStatus('Could not generate the PDF.');
      }
    }}
  >
    Download PDF
  </button>
</div>

<details>
  <summary style={{ cursor: 'pointer', padding: '10px 0' }}>
    Read saved briefing
  </summary>

  <p>{item.briefing.verdict.summary}</p>

  {item.briefing.findings.map((finding, i) => (
    <p key={i}>
      <strong>{finding.title}:</strong> {finding.explanation}
      ({finding.citation.source})
    </p>
  ))}

  {item.briefing.riskFactors.map((factor, i) => (
    <p key={i}>
      <strong>{factor.label}:</strong> {factor.detail}
    </p>
  ))}
</details>

<div style={{ textAlign: 'right', marginTop: 20 }}>
  <button
    style={{
      color: '#b42318',
      background: 'transparent',
      border: '1px solid #b42318',
      padding: '8px 12px',
      borderRadius: 6,
      cursor: 'pointer',
    }}
    onClick={() => {
      if (window.confirm(
        'Delete this saved briefing? This cannot be undone.'
      )) {
        void remove(item.id).catch(() =>
          setStatus('Could not delete briefing.')
        );
      }
    }}
  >
    Delete briefing
  </button>
</div>
    </article>)}
    <h2>Privacy controls</h2>
    <p>No account is required. Profile and saved briefing storage is local to this browser. Requests to weather, FAA and AI services may still transmit location and other necessary request details while online.</p>
    <button onClick={() => void eraseAll().catch(() => setStatus('Could not clear storage.'))}>Delete all locally saved SkyBrief data</button>
    <p><a href="/briefing">Back to briefing</a></p>
  </div></AppShell>;
}
