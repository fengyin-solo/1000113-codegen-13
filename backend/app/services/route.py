"""线路管理业务规则：草稿版本与生效版本分开存放，状态流转与站点排列都收在这里。

存储约定（内存仓库，真实项目里会换成数据库）：
- draft_sites / draft_start / draft_end：草稿版本，调整站点只动这里，刷新不丢；
- active_sites / active_start / active_end：最近一次「启用线路」正式生效的版本，
  停用后再次启用恢复的就是它；
- retained_draft：停用后再次启用时，启用前那份草稿的快照，只展示、不自动生效；
- 旧数据（「途经站点」是逗号拼接的字符串、没有版本字段）在首次访问时惰性迁移。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "route"
REQUIRED_FIELDS = ["线路编码", "线路名称", "起点冷库"]
STATUS_DRAFT = "草稿"
STATUS_ACTIVE = "已启用"
STATUS_DISABLED = "已停用"
STATUS_ORDER = [STATUS_DRAFT, STATUS_ACTIVE, STATUS_DISABLED]

# 草稿里允许调整的字段（途经站点、起点冷库、终点冷库）
EDIT_FIELDS = ["途经站点", "起点冷库", "终点冷库"]

SITE_SPLITTERS = ("、", "，", ",", ";", "；", "\n")


def split_sites(value: Any) -> list[str]:
    """把逗号/顿号拼接的途经站点拆成有序列表，自动去掉空白与重复相邻的分隔符。"""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "")
    for splitter in SITE_SPLITTERS[1:]:
        text = text.replace(splitter, SITE_SPLITTERS[0])
    return [part.strip() for part in text.split(SITE_SPLITTERS[0]) if part.strip()]


def join_sites(sites: list[str]) -> str:
    return "、".join(sites)


def _snapshot(version: dict[str, Any] | None) -> dict[str, Any] | None:
    if not version:
        return None
    return {
        "起点冷库": version.get("起点冷库", ""),
        "终点冷库": version.get("终点冷库", ""),
        "途经站点": list(version.get("途经站点") or []),
    }


class RouteService:
    # ---------- 读取 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        for row in rows:
            self._migrate(row)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("线路编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        self._migrate(entry)
        return self._present(entry)

    # ---------- 登记 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        for row in rows:
            self._migrate(row)
        code = str(values.get("线路编码") or "").strip()
        if any(row.get("线路编码") == code for row in rows):
            return None, [f"线路编码 {code} 已存在"]
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["线路编码"] = code
        entry["线路名称"] = str(values.get("线路名称") or "").strip()
        entry["起点冷库"] = str(values.get("起点冷库") or "").strip()
        entry["终点冷库"] = str(values.get("终点冷库") or "").strip()
        entry["预计时长"] = str(values.get("预计时长") or "").strip()
        entry["线路里程"] = str(values.get("线路里程") or "").strip()
        entry["status"] = STATUS_DRAFT
        entry["pending"] = True
        entry["abnormal"] = False
        entry["notice"] = ""
        entry["draft_sites"] = split_sites(values.get("途经站点"))
        entry["draft_start"] = entry["起点冷库"]
        entry["draft_end"] = entry["终点冷库"]
        entry["active_sites"]: list[str] = []
        entry["active_start"] = ""
        entry["active_end"] = ""
        entry["retained_draft"] = None
        rows.append(entry)
        return self._present(entry), []

    # ---------- 动作 ----------
    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"配送线路 {entry_id} 不存在或已归档"
        self._migrate(entry)
        values = values or {}

        if action == "调整站点":
            return self._adjust_sites(entry, values)
        if action == "启用线路":
            return self._activate(entry)
        if action == "停用线路":
            return self._disable(entry)
        if action == "回收草稿":
            return self._discard_draft(entry)
        return None, f"动作「{action}」不属于线路管理可执行范围"

    def _adjust_sites(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """调整途经站点、起点/终点冷库：只改草稿版本，不影响已生效的排列。"""
        sites = split_sites(values.get("途经站点", entry["draft_sites"]))
        start = str(values.get("起点冷库", entry["draft_start"]) or "").strip()
        end = str(values.get("终点冷库", entry["draft_end"]) or "").strip()
        if not sites:
            return None, "途经站点至少保留一个，草稿未保存"
        if not start:
            return None, "起点冷库不能为空，草稿未保存"
        entry["draft_sites"] = sites
        entry["draft_start"] = start
        entry["draft_end"] = end
        entry["draft_valid"] = True
        entry["notice"] = ""
        if entry["status"] == STATUS_DRAFT:
            return self._present(entry), "草稿已保存，启用线路后正式生效"
        return self._present(entry), "调整已保存为草稿，再次启用线路后才会正式生效"

    def _activate(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """启用线路：草稿正式生效；停用后再次启用则恢复上一次的站点排列并保留草稿快照。"""
        status = entry["status"]
        if status == STATUS_ACTIVE:
            return None, "线路已处于启用状态，无需重复启用"
        if not entry.get("draft_valid", False):
            return None, "草稿缺少完整的起点冷库与途经站点，无法启用"

        if status == STATUS_DISABLED and entry["active_sites"]:
            # 恢复上一次已启用的排列；启用前那份草稿快照保留，不随启用丢失
            entry["retained_draft"] = _snapshot(self._draft_version(entry))
            entry["status"] = STATUS_ACTIVE
            entry["pending"] = False
            entry["abnormal"] = False
            entry["notice"] = "已恢复上一次启用的站点排列，启用前的草稿已保留"
            return self._present(entry), "已恢复上一次启用的站点排列，启用前的草稿版本已保留"

        # 草稿首次启用：草稿正式生效
        entry["active_sites"] = list(entry["draft_sites"])
        entry["active_start"] = entry["draft_start"]
        entry["active_end"] = entry["draft_end"]
        entry["retained_draft"] = None
        entry["status"] = STATUS_ACTIVE
        entry["pending"] = False
        entry["abnormal"] = False
        entry["notice"] = "草稿已正式生效"
        return self._present(entry), "草稿已正式生效"

    def _disable(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry["status"] != STATUS_ACTIVE:
            return None, "只有已启用的线路可以停用"
        entry["status"] = STATUS_DISABLED
        entry["pending"] = True
        entry["abnormal"] = True
        entry["notice"] = "线路已停用，生效排列保留；再启用时恢复，当前草稿继续保留"
        return self._present(entry), "线路已停用，再次启用将恢复上一次的站点排列"

    def _discard_draft(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """草稿被回收：丢弃当前草稿并沿用上一次已启用的版本。"""
        if not entry["active_sites"]:
            return None, "该线路还没有已启用的版本，草稿不能回收"
        entry["draft_sites"] = list(entry["active_sites"])
        entry["draft_start"] = entry["active_start"]
        entry["draft_end"] = entry["active_end"]
        entry["draft_valid"] = True
        entry["notice"] = "当前草稿已回收，线路沿用上一次已启用的站点排列"
        return self._present(entry), "草稿已回收，已沿用上一次已启用的站点排列"

    # ---------- 迁移与展示 ----------
    def _migrate(self, entry: dict[str, Any]) -> None:
        """把旧格式记录补成「草稿 + 生效版本」结构；草稿残缺时按回收处理并给出说明。"""
        if "draft_sites" in entry:
            self._validate_draft(entry)
            return
        legacy_sites = split_sites(entry.get("途经站点"))
        legacy_start = str(entry.get("起点冷库") or "").strip()
        legacy_end = str(entry.get("终点冷库") or "").strip()
        had_active = entry.get("status") in (STATUS_ACTIVE, STATUS_DISABLED)
        if had_active:
            entry["active_sites"] = legacy_sites
            entry["active_start"] = legacy_start
            entry["active_end"] = legacy_end
            entry["draft_sites"] = list(legacy_sites)
            entry["draft_start"] = legacy_start
            entry["draft_end"] = legacy_end
            entry["draft_valid"] = bool(legacy_sites and legacy_start)
            entry["retained_draft"] = None
        else:
            entry["active_sites"] = []
            entry["active_start"] = ""
            entry["active_end"] = ""
            entry["draft_sites"] = legacy_sites
            entry["draft_start"] = legacy_start
            entry["draft_end"] = legacy_end
            entry["draft_valid"] = bool(legacy_sites and legacy_start)
            entry["retained_draft"] = None
        entry.setdefault("notice", "")
        self._validate_draft(entry)

    def _validate_draft(self, entry: dict[str, Any]) -> None:
        """草稿残缺（例如起点/站点被清空）时回收草稿：说明原因并沿用上一次已启用版本。"""
        valid = bool(entry.get("draft_sites")) and bool(str(entry.get("draft_start") or "").strip())
        if valid:
            entry["draft_valid"] = True
            return
        if entry.get("active_sites"):
            entry["draft_sites"] = list(entry["active_sites"])
            entry["draft_start"] = entry["active_start"]
            entry["draft_end"] = entry["active_end"]
            entry["draft_valid"] = True
            entry["notice"] = "草稿缺少起点冷库或途经站点，已回收并沿用上一次已启用的排列"
        else:
            entry["draft_valid"] = False
            entry["notice"] = "草稿缺少起点冷库或途经站点，请补全后再启用"

    def _draft_version(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "起点冷库": entry["draft_start"],
            "终点冷库": entry["draft_end"],
            "途经站点": list(entry["draft_sites"]),
        }

    def _active_version(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        if not entry["active_sites"]:
            return None
        return {
            "起点冷库": entry["active_start"],
            "终点冷库": entry["active_end"],
            "途经站点": list(entry["active_sites"]),
        }

    def _present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """对外结构：列表与详情同源，途经站点数量以当前工作版本（草稿优先）为准。"""
        draft = self._draft_version(entry)
        active = self._active_version(entry)
        working = draft if entry.get("draft_valid", False) and draft["途经站点"] else (active or draft)
        retained = _snapshot(entry.get("retained_draft"))
        result = dict(entry)
        result.pop("draft_sites", None)
        result.pop("draft_start", None)
        result.pop("draft_end", None)
        result.pop("draft_valid", None)
        result.pop("active_sites", None)
        result.pop("active_start", None)
        result.pop("active_end", None)
        result.pop("retained_draft", None)
        result["途经站点"] = join_sites(working["途经站点"])
        result["起点冷库"] = working["起点冷库"] or "—"
        result["终点冷库"] = working["终点冷库"] or "—"
        result["途经站点数量"] = len(working["途经站点"])
        result["has_draft_changes"] = bool(
            active
            and (
                draft["途经站点"] != active["途经站点"]
                or draft["起点冷库"] != active["起点冷库"]
                or draft["终点冷库"] != active["终点冷库"]
            )
        )
        result["draft_version"] = draft
        result["active_version"] = active
        result["retained_draft"] = retained
        return result
