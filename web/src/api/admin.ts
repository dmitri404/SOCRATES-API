import api from './client'

export const getUsuarios = () =>
  api.get('/admin/usuarios').then((r) => r.data)

export const getPortais = () =>
  api.get('/admin/portais').then((r) => r.data)

export const postUsuario = (data: Record<string, unknown>) =>
  api.post('/admin/usuarios', data).then((r) => r.data)

export const patchUsuario = (id: string, data: Record<string, unknown>) =>
  api.patch(`/admin/usuarios/${id}`, data).then((r) => r.data)

export const resetarSenha = (id: string) =>
  api.post(`/admin/usuarios/${id}/resetar-senha`).then((r) => r.data)

export const putPortais = (id: string, portais: { slug: string; pode_editar: boolean }[]) =>
  api.put(`/admin/usuarios/${id}/portais`, { portais }).then((r) => r.data)
