import api from './client'

export const getConfGeral = (portal: string) =>
  api.get(`/conf/${portal}/geral`).then((r) => r.data)

export const putConfGeral = (portal: string, data: Record<string, unknown>) =>
  api.put(`/conf/${portal}/geral`, data).then((r) => r.data)

export const getCredores = (portal: string) =>
  api.get(`/conf/${portal}/credores`).then((r) => r.data)

export const postCredor = (portal: string, data: Record<string, unknown>) =>
  api.post(`/conf/${portal}/credores`, data).then((r) => r.data)

export const deleteCredor = (portal: string, id: number) =>
  api.delete(`/conf/${portal}/credores/${id}`).then((r) => r.data)

export const toggleCredor = (portal: string, id: number) =>
  api.patch(`/conf/${portal}/credores/${id}/toggle`).then((r) => r.data)

export const getEmails = (portal: string) =>
  api.get(`/conf/${portal}/emails`).then((r) => r.data)

export const postEmail = (portal: string, data: Record<string, unknown>) =>
  api.post(`/conf/${portal}/emails`, data).then((r) => r.data)

export const deleteEmail = (portal: string, id: number) =>
  api.delete(`/conf/${portal}/emails/${id}`).then((r) => r.data)

export const toggleEmail = (portal: string, id: number) =>
  api.patch(`/conf/${portal}/emails/${id}/toggle`).then((r) => r.data)

export const getExercicios = (portal: string) =>
  api.get(`/conf/${portal}/exercicios`).then((r) => r.data)

export const postExercicio = (portal: string, data: Record<string, unknown>) =>
  api.post(`/conf/${portal}/exercicios`, data).then((r) => r.data)

export const deleteExercicio = (portal: string, id: number) =>
  api.delete(`/conf/${portal}/exercicios/${id}`).then((r) => r.data)

export const toggleExercicio = (portal: string, id: number) =>
  api.patch(`/conf/${portal}/exercicios/${id}/toggle`).then((r) => r.data)

export const triggerPortal = (portal: string) =>
  api.post(`/${portal}/trigger`).then((r) => r.data)
