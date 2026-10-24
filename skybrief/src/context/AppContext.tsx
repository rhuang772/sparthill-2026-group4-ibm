import React, { createContext, useContext, useState } from 'react';
import type { PilotProfile, FlightPlan } from '../types';

interface AppContextValue {
  pilotProfile: PilotProfile | null;
  setPilotProfile: (profile: PilotProfile) => void;
  flightPlan: FlightPlan | null;
  setFlightPlan: (plan: FlightPlan) => void;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [pilotProfile, setPilotProfile] = useState<PilotProfile | null>(null);
  const [flightPlan, setFlightPlan] = useState<FlightPlan | null>(null);

  return (
    <AppContext.Provider value={{ pilotProfile, setPilotProfile, flightPlan, setFlightPlan }}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}
