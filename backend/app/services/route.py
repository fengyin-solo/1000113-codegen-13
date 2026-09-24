"""线路管理业务规则：草稿/正式版本分离、状态流转、字段校验与筛选口径都收在这里。

每条线路同时维护两份站点排列：
- active：上一次「启用线路」时正式生效的排列，停用不会丢失，再启用时原样恢复；
- draft ：调整站点时使用的草稿，随改随存，刷新和返回列表再进来都还在，
  直到「启用线路」时才正式发布。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "route"
REQUIRED_FIELDS = ["线路编码", "线路名称", "起点冷库"]
EDIT_FIELDS = ["线路名称", "起点冷库", "终点冷库", "预计时长", "线路里程"]
STATUS_ORDER = ["草稿", "已启用", "已停用"]
DRAFT_STATUS = STATUS_ORDER[0]
ACTIVE_STATUS = STATUS_ORDER[1]
DISABLED_STATUS = STATUS_ORDER[2]

ACTION_RULES = {"启用线路": "已启用", "调整站点": "草稿", "停用线路": "已停用"}
NEGATIVE_ACTIONS = ["停用线路"]

# 版本内会保存的排列字段；线路编码不属于排列，不进版本
REVISION_FIELDS = ["线路名称", "起点冷库", "终点冷库", "途经站点", "预计时长", "线路里程"]


def _to_stations(raw: Any) -> list[str]:
    """把途经站点归一成有序列表：兼容数组、顿号/逗号分隔的字符串，去掉空白项。"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = raw
    else:
        text = str(raw)
        for separator in ("、", "，", ",", ";", "；", "|", "\n"):
            text = text.replace(separator, "、")
        items = text.split("、")
    return [str(item).strip() for item in items if str(item).strip()]


def _build_revision(source: dict[str, Any]) -> dict[str, Any]:
    revision = {field: source.get(field) for field in REVISION_FIELDS}
    stations = _to_stations(source.get("途经站点"))
    revision["途经站点"] = stations
    revision["站点数"] = len(stations)
    return revision


def _sync_from_revision(entry: dict[str, Any], revision: dict[str, Any]) -> None:
    """让顶层展示字段与指定版本保持一致。"""
    for field in REVISION_FIELDS:
        entry[field] = revision.get(field)


class RouteService:
    def __init__(self) -> None:
        # 内存仓库重启后会回到种子数据；老结构的种子数据在这里补齐版本字段
        for row in store.rows(MODULE):
            if "active" not in row and "draft" not in row:
                self._upgrade_legacy(row)

    def _upgrade_legacy(self, entry: dict[str, Any]) -> None:
        revision = _build_revision(entry)
        status = entry.get("status")
        entry["active"] = revision if status in (ACTIVE_STATUS, DISABLED_STATUS) else None
        entry["active_status"] = status if isinstance(entry["active"], dict) else None
        entry["draft"] = revision if status == DRAFT_STATUS else None
        entry["draft_source"] = None
        entry["notice"] = None
        _sync_from_revision(entry, revision)

    def present_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表与详情共用的展示口径：站点数量由同一份有序列表计算，避免两处对不上。"""
        data = dict(entry)
        stations = _to_stations(entry.get("途经站点"))
        data["途经站点"] = stations
        data["站点数"] = len(stations)
        data["active"] = self._present_revision(entry.get("active"))
        data["draft"] = self._present_revision(entry.get("draft"))
        return data

    @staticmethod
    def _present_revision(revision: Any) -> dict[str, Any] | None:
        if not isinstance(revision, dict):
            return None
        data = dict(revision)
        data["途经站点"] = _to_stations(revision.get("途经站点"))
        data["站点数"] = len(data["途经站点"])
        return data

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("线路编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.present_entry(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self.present_entry(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["线路编码"] = values.get("线路编码")
        for field in EDIT_FIELDS:
            entry[field] = values.get(field)
        entry["途经站点"] = _to_stations(values.get("途经站点"))
        entry["status"] = DRAFT_STATUS
        entry["pending"] = True
        entry["abnormal"] = False
        # 新登记的线路只有草稿版本，还没有任何一次正式生效的排列
        draft = _build_revision(entry)
        entry["draft"] = draft
        entry["active"] = None
        entry["active_status"] = None
        entry["draft_source"] = None
        entry["notice"] = None
        _sync_from_revision(entry, draft)
        rows.append(entry)
        return self.present_entry(entry), []

    def save_draft(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """把草稿改动落到本地一份：刷新、返回列表再重新进入都不丢。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"配送线路 {entry_id} 不存在或已归档"
        if entry.get("status") != DRAFT_STATUS:
            return None, "只有草稿状态的线路可以保存草稿，请先执行「调整站点」"
        draft = entry.get("draft")
        if not isinstance(draft, dict):
            return None, "没有可保存的草稿，请先执行「调整站点」"
        # 只改草稿版本，顶层展示字段在草稿态与草稿保持一致；正式版本一行都不动
        for field in EDIT_FIELDS:
            if field in values and values.get(field) is not None:
                draft[field] = values.get(field)
        if "途经站点" in values:
            draft["途经站点"] = _to_stations(values.get("途经站点"))
        draft["站点数"] = len(draft["途经站点"])
        entry["notice"] = None
        _sync_from_revision(entry, draft)
        return self.present_entry(entry), "草稿已保存在本地，刷新或返回列表后改动仍在"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"配送线路 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于线路管理可执行范围"
        status = entry.get("status")

        if action == "启用线路":
            return self._activate(entry, status)
        if action == "停用线路":
            return self._disable(entry, status)
        return self._adjust(entry, status)

    def _activate(self, entry: dict[str, Any], status: str) -> tuple[dict[str, Any] | None, str]:
        active = entry.get("active")
        draft = entry.get("draft")

        # 已停用后再次启用：恢复上一次正式启用的站点排列，启用前保留的草稿不动
        if status == DISABLED_STATUS and isinstance(active, dict):
            entry["status"] = ACTIVE_STATUS
            entry["active_status"] = ACTIVE_STATUS
            entry["pending"] = True
            entry["abnormal"] = False
            _sync_from_revision(entry, active)
            message = "已恢复上一次启用的站点排列，启用前的草稿版本仍然保留"
            if entry.get("notice"):
                message = f"{entry['notice']}；{message}"
            return self.present_entry(entry), message

        if status == ACTIVE_STATUS:
            return None, "线路已处于启用状态，沿用上一次正式生效的排列，无需重复启用"

        if status != DRAFT_STATUS:
            return None, "当前状态不支持启用线路"

        if not isinstance(draft, dict):
            return None, "没有可发布的草稿，请先调整站点"

        stations = _to_stations(draft.get("途经站点"))
        if not stations:
            # 草稿被调整坏了（站点全部丢失）：回收草稿，沿用上一次已启用的版本并说明
            if isinstance(active, dict):
                return self._revert_to_active(entry, "草稿途经站点为空，已回收草稿并沿用上一次已启用的版本")
            return None, "草稿的途经站点为空，无法启用，请至少保留一个站点"

        if not str(draft.get("起点冷库") or "").strip():
            return None, "草稿缺少起点冷库，无法启用，请补全后再发布"

        # 草稿正式生效：发布为 active，草稿版本随之清空
        entry["active"] = _build_revision(draft)
        entry["active_status"] = ACTIVE_STATUS
        entry["draft"] = None
        entry["draft_source"] = None
        entry["notice"] = None
        entry["status"] = ACTIVE_STATUS
        entry["pending"] = True
        entry["abnormal"] = False
        _sync_from_revision(entry, entry["active"])
        return self.present_entry(entry), "草稿已正式生效，站点排列已发布"

    def _disable(self, entry: dict[str, Any], status: str) -> tuple[dict[str, Any] | None, str]:
        if status == DISABLED_STATUS:
            return None, "线路已处于停用状态，无需重复停用"
        if status == DRAFT_STATUS and not isinstance(entry.get("active"), dict):
            return None, "草稿尚未启用过，不能停用；请先启用或继续调整草稿"
        # 停用只冻结正式版本：active 原样保留，草稿也原样保留，再次启用时恢复
        entry["status"] = DISABLED_STATUS
        entry["active_status"] = DISABLED_STATUS
        entry["pending"] = False
        entry["abnormal"] = True
        _sync_from_revision(entry, entry["active"])
        suffix = "，调整中的草稿已一并保留" if isinstance(entry.get("draft"), dict) else ""
        return self.present_entry(entry), f"配送线路已停用，当前站点排列已保留{suffix}"

    def _adjust(self, entry: dict[str, Any], status: str) -> tuple[dict[str, Any] | None, str]:
        if status == DRAFT_STATUS:
            return None, "线路已在草稿调整中，直接保存草稿即可，无需重复调整"
        active = entry.get("active")
        if not isinstance(active, dict):
            return None, "线路缺少可调整的正式版本，请先登记草稿"
        # 进入调整：若之前已留下草稿（如停用后再调整），续用旧草稿；否则从正式版本拷一份
        if isinstance(entry.get("draft"), dict):
            revision = entry["draft"]
            message = "已打开调整站点，沿用之前保留的草稿版本"
        else:
            revision = _build_revision(active)
            entry["draft"] = revision
            entry["draft_source"] = status
            message = "已从当前站点排列复制一份草稿，改动在启用前不会影响正式线路"
        entry["status"] = DRAFT_STATUS
        entry["pending"] = True
        entry["abnormal"] = False
        entry["notice"] = None
        _sync_from_revision(entry, revision)
        return self.present_entry(entry), message

    def _revert_to_active(self, entry: dict[str, Any], notice: str) -> tuple[dict[str, Any], str]:
        """草稿被回收：说明原因，状态与展示内容回退到上一次已启用的版本。"""
        active = entry.get("active")
        restore_status = entry.get("active_status") or ACTIVE_STATUS
        entry["draft"] = None
        entry["draft_source"] = None
        entry["status"] = restore_status
        entry["pending"] = restore_status != DISABLED_STATUS
        entry["abnormal"] = restore_status == DISABLED_STATUS
        entry["notice"] = notice
        if isinstance(active, dict):
            _sync_from_revision(entry, active)
        return self.present_entry(entry), notice

    def discard_draft(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"配送线路 {entry_id} 不存在或已归档"
        if not isinstance(entry.get("active"), dict):
            return None, "该草稿从未启用过，没有可沿用的历史版本；请直接修改草稿内容"
        return self._revert_to_active(entry, "草稿已回收，列表与详情均沿用上一次已启用的版本")
