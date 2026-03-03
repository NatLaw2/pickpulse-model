import { useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { useAuth } from '../lib/AuthContext';

export function LoginPage() {
  const { signIn, signUp } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [signUpSuccess, setSignUpSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isSignUp) {
        await signUp(email, password);
        setSignUpSuccess(true);
      } else {
        await signIn(email, password);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)]">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-2">
            <ShieldAlert size={24} className="text-[var(--color-accent)]" />
            <h1 className="text-lg font-bold tracking-wide text-[var(--color-accent-glow)]">
              PICKPULSE
            </h1>
          </div>
          <p className="text-xs text-[var(--color-text-muted)] tracking-widest uppercase">
            Intelligence Platform
          </p>
        </div>

        <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-2xl p-6">
          <h2 className="text-base font-semibold text-[var(--color-text-primary)] mb-4">
            {isSignUp ? 'Create Account' : 'Sign In'}
          </h2>

          {signUpSuccess ? (
            <div className="text-sm text-green-400 bg-green-400/10 border border-green-400/20 rounded-lg p-3">
              Check your email for a confirmation link, then sign in.
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg text-sm text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]/50"
                  placeholder="you@company.com"
                />
              </div>
              <div>
                <label className="block text-xs text-[var(--color-text-muted)] mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className="w-full px-3 py-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg text-sm text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]/50"
                  placeholder="Min 6 characters"
                />
              </div>

              {error && (
                <div className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent)]/90 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {loading ? 'Please wait...' : isSignUp ? 'Create Account' : 'Sign In'}
              </button>
            </form>
          )}

          <div className="mt-4 text-center">
            <button
              onClick={() => {
                setIsSignUp(!isSignUp);
                setError('');
                setSignUpSuccess(false);
              }}
              className="text-xs text-[var(--color-accent)] hover:underline"
            >
              {isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
