import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Compass, Mail } from 'lucide-react';
import api from '../services/api';

const ForgotPassword: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email.trim()) {
      setError('Please enter your email address.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/forgot-password', { email: email.trim() });
      navigate('/verify-otp', { state: { email: email.trim() } });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not send reset OTP. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4 relative overflow-hidden">
      <div className="glow-bg top-[20%] left-[20%]" />
      <div className="glow-bg bottom-[20%] right-[20%]" />

      <div className="glass-panel w-full max-w-md p-8 relative z-10">
        <div className="flex flex-col items-center mb-8">
          <Link to="/" className="bg-brand-500 hover:bg-brand-600 p-2.5 rounded-2xl text-white mb-4 transition-all duration-200 flex items-center justify-center shadow-sm">
            <Compass size={28} />
          </Link>
          <h2 className="text-2xl font-bold text-white mb-1">Forgot Password</h2>
          <p className="text-slate-400 text-sm">Receive a 6 digit OTP to reset your password</p>
        </div>

        {error && (
          <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-3 rounded-xl mb-5">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
              Email Address
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-500 pointer-events-none">
                <Mail size={16} />
              </span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@university.edu"
                className="w-full glass-input pl-10"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-3 px-4 flex items-center justify-center gap-2"
          >
            <span>{loading ? 'Sending OTP...' : 'Send OTP'}</span>
            {!loading && <ArrowRight size={16} />}
          </button>
        </form>

        <p className="text-center text-slate-400 text-sm mt-6">
          Remember your password?{' '}
          <Link to="/login" className="text-brand-400 hover:text-brand-300 font-semibold transition-colors">
            Sign In
          </Link>
        </p>
      </div>
    </div>
  );
};

export default ForgotPassword;
