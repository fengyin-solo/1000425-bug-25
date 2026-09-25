import { defineStore } from 'pinia'

export const ROLES = ['申请人', '监护人', '签发人'] as const
export const TEAMS = ['运行一班', '运行二班', '检修班'] as const

export type Role = (typeof ROLES)[number]
export type Team = (typeof TEAMS)[number]

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '签发人' as Role,
    team: '运行一班' as Team,
    shiftLabel: '白班 08:00-20:00',
    scope: '污水处理厂工艺管控平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setIdentity(role: Role, team: Team, operator?: string) {
      this.role = role
      this.team = team
      if (operator) {
        this.operator = operator
      }
    },
  },
})
