import { Navigate, Route, Routes } from 'react-router-dom';
import { useState } from 'react';
import Navbar from './components/Navbar.jsx';
import Dashboard from './pages/Dashboard.jsx';
import DealDetails from './pages/DealDetails.jsx';
import Login from './pages/Login.jsx';
import ManufactureData from './pages/ManufactureData.jsx';
import NewDeal from './pages/NewDeal.jsx';
import NarrativesWorkspace from './pages/NarrativesWorkspace.jsx';

export default function App() {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('creditPitchUser');
    return saved ? JSON.parse(saved) : null;
  });

  const handleLogin = (nextUser) => {
    localStorage.setItem('creditPitchUser', JSON.stringify(nextUser));
    setUser(nextUser);
  };

  const handleLogout = () => {
    localStorage.removeItem('creditPitchUser');
    setUser(null);
  };

  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-[#F5F7FA]">
      <Navbar user={user} onLogout={handleLogout} />
      <main className="mx-auto w-full max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new-deal" element={<NewDeal />} />
          <Route path="/manufacture-data" element={<ManufactureData />} />
          <Route path="/deals/:id" element={<DealDetails />} />
          <Route path="/deals/:id/narratives" element={<NarrativesWorkspace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
