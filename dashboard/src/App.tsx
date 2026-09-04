import { NavLink, Route, Routes, Navigate } from 'react-router-dom';
import { OverviewPage } from './pages/OverviewPage';
import { DatasetsPage } from './pages/DatasetsPage';
import { JobsPage } from './pages/JobsPage';
import { AlertsPage } from './pages/AlertsPage';
import { MapPage } from './pages/MapPage';
import { EvidencePage } from './pages/EvidencePage';

const NAV = [
  { to: '/overview', label: 'Overview' },
  { to: '/datasets', label: 'Datasets' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/alerts', label: 'Alerts' },
  { to: '/map', label: 'Map' },
  { to: '/evidence', label: 'Lineage' },
];

export function App() {
  return (
    <div className="app-shell">
      <nav className="sidebar" aria-label="Primary">
        <div className="sidebar__brand">
          Marine Data Layer
          <small>Operations dashboard</small>
        </div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/datasets" element={<DatasetsPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/evidence" element={<EvidencePage />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
    </div>
  );
}
