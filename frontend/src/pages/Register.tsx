import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Compass, Mail, Lock, UserPlus, CheckCircle, Eye, EyeOff } from 'lucide-react';

const passwordErrors = (password: string) => {
  const errors: string[] = [];
  if (password.length < 8) errors.push('Minimum length is 8 characters.');
  if (password.length > 64) errors.push('Maximum length is 64 characters.');
  if (!/[A-Z]/.test(password)) errors.push('Include at least 1 uppercase letter.');
  if (!/[a-z]/.test(password)) errors.push('Include at least 1 lowercase letter.');
  if (!/\d/.test(password)) errors.push('Include at least 1 number.');
  if (!/[^A-Za-z0-9]/.test(password)) errors.push('Include at least 1 special character.');
  return errors;
};

const Register: React.FC = () => {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!email || !password || !confirmPassword) {
      setError('Please fill in all fields.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    const validationErrors = passwordErrors(password);
    if (validationErrors.length > 0) {
      setError(validationErrors[0]);
      return;
    }

    setLoading(true);
    try {
      await register(email, password);
      setSuccess(true);
      setTimeout(() => {
        navigate('/login');
      }, 2000);
    } catch (err: any) {
      setError(
        err.response?.data?.detail || 'Registration failed. Check details or email format.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4 relative overflow-hidden">
      <div className="glow-bg top-[20%] left-[20%]" />
      <div className="glow-bg bottom-[20%] right-[20%]" />

      <div className="glass-panel w-full max-w-md p-8 relative z-10">
        {/* Header */}
        <div className="flex flex-col items-center mb-8">
          <Link to="/" className="bg-brand-500 hover:bg-brand-600 p-2.5 rounded-2xl text-white mb-4 transition-all duration-200 flex items-center justify-center shadow-sm">
            <Compass size={28} />
          </Link>
          <h2 className="text-2xl font-bold text-white mb-1">Create Account</h2>
          <p className="text-slate-400 text-sm">Join ResearchPilot AI hub and start indexing</p>
        </div>

        {/* Success / Error alerts */}
        {success ? (
          <div className="bg-emerald-950 bg-opacity-40 border border-emerald-900 border-opacity-50 text-emerald-300 text-sm px-4 py-3.5 rounded-xl mb-5 flex items-center gap-3">
            <CheckCircle size={18} className="text-emerald-400 shrink-0" />
            <span>Registration successful! Redirecting to login...</span>
          </div>
        ) : (
          error && (
            <div className="bg-red-950 bg-opacity-40 border border-red-900 border-opacity-50 text-red-300 text-sm px-4 py-3 rounded-xl mb-5">
              {error}
            </div>
          )
        )}

        {/* Form */}
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
                disabled={success}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
              Password
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-500 pointer-events-none">
                <Lock size={16} />
              </span>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Research@123"
                className="w-full glass-input pl-10 pr-10"
                required
                disabled={success}
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-500 hover:text-slate-300"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                disabled={success}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {password && passwordErrors(password).length > 0 && (
              <div className="mt-2 space-y-1 text-xs text-amber-300">
                {passwordErrors(password).map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
              Confirm Password
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center text-slate-500 pointer-events-none">
                <Lock size={16} />
              </span>
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter password"
                className="w-full glass-input pl-10 pr-10"
                required
                disabled={success}
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword((value) => !value)}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-500 hover:text-slate-300"
                aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                disabled={success}
              >
                {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {confirmPassword && password !== confirmPassword && (
              <p className="mt-2 text-xs text-red-300">Passwords do not match</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || success || passwordErrors(password).length > 0 || password !== confirmPassword}
            className="btn-primary w-full py-3 px-4 flex items-center justify-center gap-2"
          >
            <UserPlus size={16} />
            <span>{loading ? 'Creating...' : 'Register'}</span>
          </button>
        </form>

        <p className="text-center text-slate-400 text-sm mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-brand-400 hover:text-brand-300 font-semibold transition-colors">
            Sign In instead
          </Link>
        </p>
      </div>
    </div>
  );
};

export default Register;
