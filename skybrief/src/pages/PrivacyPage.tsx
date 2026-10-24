import { useState } from 'react';
import AppShell from '../components/AppShell';
import { useAppContext } from '../context/AppContext';

export default function PrivacyPage() {
  const [status, setStatus] = useState('');
  const { resetPrivateData } = useAppContext();

  async function eraseLocalData() {
    if (!window.confirm('Delete the locally saved SkyBrief profile and flight plan from this device?')) return;
    await resetPrivateData();
    setStatus('Locally saved profile and flight plan deleted.');
  }

  return (
    <AppShell currentStep={3}>
      <div style={{ maxWidth: 800, margin: '2rem auto', padding: '0 1rem' }}>
        <h1>Privacy &amp; Local Data</h1>
        <p>
          Briefing PDFs are downloaded to the location chosen by your browser. SkyBrief does not
          keep a copy of those PDFs in its local database; remove downloaded files using your
          device&apos;s file manager.
        </p>
        <p>
          Your profile and flight plan preferences are stored in this browser&apos;s local storage.
          Weather, FAA and AI requests may transmit location and other necessary request details
          while online.
        </p>
        <p role="status">{status}</p>
        <button onClick={() => void eraseLocalData().catch(() => setStatus('Could not clear local data.'))}>
          Delete locally saved profile and flight plan
        </button>
        <p><a href="/briefing">Back to briefing</a></p>
      </div>
    </AppShell>
  );
}
