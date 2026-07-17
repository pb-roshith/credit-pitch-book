import { BookOpen, LogIn, UserPlus } from 'lucide-react';
import { useState } from 'react';
import { login, register } from '../services/api.js';

export default function Login({ onLogin }) {
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);

    try {
      const action = mode === 'login' ? login : register;
      const user = await action({ username, password });
      onLogin(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-[#F5F7FA] px-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-enterprise">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-lg bg-[#003A8C] text-white">
            <BookOpen size={22} />
          </span>
          <div>
            <h1 className="text-xl font-bold text-slate-950">Credit Pitch Book</h1>
            <p className="text-sm font-semibold text-slate-500">{mode === 'login' ? 'Sign in' : 'Create user'}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-wide text-slate-500">User Name</label>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
              autoComplete="username"
            />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-wide text-slate-500">Password</label>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#003A8C] focus:ring-2 focus:ring-blue-100"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
          </div>

          {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>}

          <button
            type="submit"
            disabled={loading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[#003A8C] px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {mode === 'login' ? <LogIn size={17} /> : <UserPlus size={17} />}
            {loading ? 'Please wait...' : mode === 'login' ? 'Login' : 'Create User'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => {
            setError('');
            setMode(mode === 'login' ? 'register' : 'login');
          }}
          className="mt-4 w-full rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700"
        >
          {mode === 'login' ? 'Create user' : 'Back to login'}
        </button>
      </div>
    </div>
  );
}
