import api from './client'

export const login = (usuario: string, senha: string) =>
  api.post('/auth/login', { usuario, senha }).then((r) => r.data)

export const logout = () =>
  api.post('/auth/logout').then((r) => r.data)

export const me = () =>
  api.get('/auth/me').then((r) => r.data)

export const alterarSenha = (senha_atual: string, senha_nova: string) =>
  api.post('/auth/alterar-senha', { senha_atual, senha_nova }).then((r) => r.data)
