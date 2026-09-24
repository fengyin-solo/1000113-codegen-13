/** 线路管理：草稿/正式版本在接口上共用同一份排列结构。 */
export interface RouteRevision {
  起点冷库: string | null
  终点冷库: string | null
  途经站点: string[]
  预计时长: string | null
  线路里程: string | null
  站点数: number
}

export interface RouteEntry {
  id: number
  status: string
  pending?: boolean
  abnormal?: boolean
  线路编码: string
  线路名称: string | null
  起点冷库: string | null
  终点冷库: string | null
  途经站点: string[]
  预计时长: string | null
  线路里程: string | null
  站点数: number
  active: RouteRevision | null
  active_status?: string | null
  draft: RouteRevision | null
  draft_source?: string | null
  notice?: string | null
}

export interface RouteActionResult {
  ok: boolean
  message: string
  entry: RouteEntry | null
}
