import { http } from './http'
import type { UserEntitlements } from '../types/engagement'

export async function fetchEntitlements(): Promise<UserEntitlements> {
  const { data } = await http.get<UserEntitlements>('/entitlements/me')
  return data
}
