import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Compass, KeyRound, Mail } from 'lucide-react';
import api from '../services/api';

const VerifyOTP: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const initialEmail = (location.state as { email?: string } | null)?.email || '';
  const [email, setEmail] = useState(initialEmail);
  const [otp, setOtp] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendCountdown, setResendCountdown] = useState(30);

  useEffect(() => {
    if (resendCountdown <= 0) return;
    const timer = window.setTimeout(() => setResendCountdown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [resendCountdown]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setMessage('');
    if (!email.trim() || otp.length !== 6) {
      setError('Enter your email and the 6 digit OTP.');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/auth/verify-otp', {
        email: email.trim(),
        otp,
      });
      navigate('/reset-password', {
        state: { email: email.trim(), resetToken: response.data.reset_token },
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid or expired OTP.');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    setMessage('');
    if (!email.trim()) {
      setError('Enter your email before requesting a new OTP.');
      return;
    }
    setResending(true);
    try {
      const response = await api.post('/auth/resend-otp', { email: email.trim() });
      setMessage(response.data.message || 'If an account exists for this email, a verification code has been sent.');
      setOtp('');
      setResendCountdown(30);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not resend OTP. Please try again later.');
    } finally {
      setResending(false);
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
          <h2 className="text-2xl font-bold text-white mb-1">Verify OTP</h2>
          <p className="text-slate-400 text-sm">Enter the 6 digit code sent to your email</p>
        </div>

        {error && (
          <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-3 rounded-xl mb-5">
            {error}
          </div>
        )}
        {message && (
          <div className="bg-emerald-950 bg-opacity-40 border border-emerald-900 border-opacity-50 text-emerald-300 text-sm px-4 py-3 rounded-xl mb-5">
            {message}
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
                className="w-full glass-input pl-10"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
              OTP
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-500 pointer-events-none">
                <KeyRound size={16} />
              </span>
              <input
                type="text"
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="123456"
                className="w-full glass-input pl-10"
                inputMode="numeric"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-3 px-4 flex items-center justify-center gap-2"
          >
            <span>{loading ? 'Verifying...' : 'Verify OTP'}</span>
            {!loading && <ArrowRight size={16} />}
          </button>

          <button
            type="button"
            onClick={handleResend}
            disabled={resending || resendCountdown > 0}
            className="btn-secondary w-full py-3 px-4 flex items-center justify-center gap-2"
          >
            {resending
              ? 'Sending...'
              : resendCountdown > 0
                ? `Resend OTP in ${resendCountdown}s`
                : 'Resend OTP'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default VerifyOTP;
