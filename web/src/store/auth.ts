import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Portal {
  slug: string
  nome: string
  pode_editar: boolean
}

export interface User {
  id: string
  email: string
  nome: string
  role: 'admin' | 'supervisor' | 'usuario'
  senha_temp: boolean
  portais: Portal[]
}

interface AuthState {
  token: string | null
  user: User | null
  setAuth: (token: string, user: User) => void
  setUser: (user: User) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      setUser: (user) => set({ user }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: 'socrates-auth' }
  )
)
