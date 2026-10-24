import { Routes, Route } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import FlightPlanPage from './pages/FlightPlanPage';
import BriefingPage from './pages/BriefingPage';
import LessonPage from './pages/LessonPage';
import ChatPage from './pages/ChatPage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/flight-plan" element={<FlightPlanPage />} />
      <Route path="/briefing" element={<BriefingPage />} />
      <Route path="/lesson" element={<LessonPage />} />
      <Route path="/chat" element={<ChatPage />} />
    </Routes>
  );
}
