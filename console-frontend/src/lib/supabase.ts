import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

console.log('[supabase.ts] URL =', supabaseUrl);
console.log('[supabase.ts] anon key loaded =', !!supabaseAnonKey);

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn('[supabase.ts] Supabase env vars missing — auth will not work');
}

export const supabase = createClient(supabaseUrl || '', supabaseAnonKey || '', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    storageKey: `sb-${new URL(supabaseUrl || 'https://placeholder.supabase.co').hostname.split('.')[0]}-auth-token`,
  },
});
