import { defineStore } from 'pinia'

// 与后端受控口径保持一致：角色决定能不能签发/驳回，班组决定签哪一张
export const OPERATOR_ROLES = ['申请人', '班组长', '安全员', '值班管理员']
export const OPERATOR_TEAMS = ['运行一班', '运行二班', '检修班']

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '值班管理员',
    team: '运行一班',
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
  },
})
