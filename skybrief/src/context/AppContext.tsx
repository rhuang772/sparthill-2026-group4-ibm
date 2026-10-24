import React, { createContext, useContext, useState } from 'react';
import type { PilotProfile, FlightPlan } from '../types';
import { clearPrivateData, savePreferences } from '../services/offlineStorage';

interface AppContextValue {
  pilotProfile: PilotProfile | null;
  setPilotProfile: (profile: PilotProfile) => void;
  flightPlan: FlightPlan | null;
  setFlightPlan: (plan: FlightPlan) => void;
  resetPrivateData: () => Promise<void>;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  // Each page load starts clean — profile/plan are still written to local
  // storage below (so "Delete all locally saved data" has something real to
  // clear), but we don't read them back in on mount, so a refresh doesn't
  // repopulate the form with a previous session's answers.
  const [pilotProfile, updatePilotProfile] = useState<PilotProfile | null>(null);
  const [flightPlan, updateFlightPlan] = useState<FlightPlan | null>(null);

  function setPilotProfile(profile: PilotProfile) {
    savePreferences('profile', profile);
    updatePilotProfile(profile);
  }

  function setFlightPlan(plan: FlightPlan) {
    savePreferences('flightPlan', plan);
    updateFlightPlan(plan);
  }

  async function resetPrivateData() {
    await clearPrivateData();
    updatePilotProfile(null);
    updateFlightPlan(null);
  }

  return (
    <AppContext.Provider value={{ pilotProfile, setPilotProfile, flightPlan, setFlightPlan, resetPrivateData }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}
