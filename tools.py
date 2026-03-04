import asyncio
import os
from typing import Optional
import httpx
from pydantic import BaseModel

# 模块顶层常量（必须在模块加载时读取一次）
# 支持环境变量覆盖，与 debug_init_houses.py 一致；tools 不创建 client，client 由 main 传入且已设置 trust_env=False 不走代理
RENTAL_API_BASE = os.environ.get("RENTAL_API_BASE", "http://7.225.29.223:8080")
USER_ID = os.environ["USER_ID"]  # 模块加载时读取，不在函数内读取


def _get_headers() -> dict:
    return {"X-User-ID": USER_ID.encode("utf-8")}


# ── Story 8.1: UserPreferences 数据模型 ─────────────────────────────────────

DISTRICTS = {"海淀", "朝阳", "通州", "昌平", "大兴", "房山", "西城", "丰台", "顺义", "东城"}

# 模块级全局映射表，由 build_area_district_map 填充（启动时由 main.py 调用）
AREA_TO_DISTRICT: dict[str, str] = {}

# 模块级地标名称集合，由 build_landmark_names 填充（启动时由 main.py 调用）
LANDMARK_NAMES: set[str] = set()

# 标签参考表（与 intent_interface_design_v2 4.1 一致，供 prompt 与过滤使用）
TAG_REFERENCE: dict[str, list[str]] = {
    "宠物": ["可养猫", "可养狗", "可养宠物", "不可养宠物", "仅限小型犬", "可养宠物需宠物押金"],
    "付款周期": ["月付", "季付", "半年付", "年付"],
    "押金": ["押一", "押二", "押三"],
    "中介/房源": ["房东直租", "收中介费"],
    "合同/房东": ["合同规范条款清晰", "合同不规范", "房东好沟通", "房东不配合", "房东难联系"],
    "看房方式": ["仅线下看房", "仅线上VR看房", "仅线上AR看房", "仅线上图片看房", "线下+线上"],
    "看房时间": [
        "全天可看房", "仅周末看房", "仅工作日看房", "工作日9-18点", "工作日14-18点",
        "工作日9-12点", "周末9-18点", "周末14-18点", "周末9-12点",
    ],
    "租期": ["可月租", "可租2个月", "可租3个月", "可租4个月", "可租5个月", "可半年租", "可年租", "仅接受年租"],
    "费用包含": [
        "包水电费", "免水电费", "水电费另付", "免宽带费", "包宽带", "网费另付",
        "包物业费", "免物业费", "物业费另付", "包车位", "免车位费", "车位费另付",
        "包取暖费", "免取暖费", "取暖费另付",
    ],
    "退租/转租": ["提前退租可协商", "提前退租扣押金", "经同意可转租", "不可转租"],
    "小区管理": [
        "车库车位", "露天车位", "无车位", "24小时保安", "门禁刷卡", "门禁形同虚设",
        "无门禁", "物业管理到位", "物业管理差", "绿化好环境佳", "绿化少环境一般",
    ],
    "周边配套": ["近公园", "近学校", "近菜市场", "近银行", "近医院", "近餐饮", "近健身房", "近警察局", "近商超", "近加油站"],
    "房屋特点": ["采光好", "南北通透", "高性价比"],
    "属性标签（软约束时用直接参数 decoration/elevator/orientation/floor_pref/rental_type）": [
        "有电梯", "精装修", "简装", "豪华装修", "朝南", "朝北", "朝东", "朝西", "西北",
        "高层", "低层", "整租", "合租",
    ],
}


class UserPreferences(BaseModel):
    # ── 位置 ──
    location: Optional[list[str]] = None
    clear_location: bool = False
    districts: Optional[list[str]] = None
    areas: Optional[list[str]] = None
    landmark_queries: Optional[list[str]] = None

    # ── API 硬约束 ──
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    bedrooms: Optional[str] = None
    rental_type: Optional[str] = None
    decoration: Optional[str] = None
    elevator: Optional[bool] = None
    orientation: Optional[str] = None
    floor_pref: Optional[str] = None
    min_area: Optional[int] = None
    max_area: Optional[int] = None
    max_subway_dist: Optional[int] = None
    subway_line: Optional[str] = None
    utilities_type: Optional[str] = None
    property_type: Optional[str] = None
    listing_platform: Optional[str] = None
    available_before: Optional[str] = None
    max_commute_minutes: Optional[int] = None
    noise_preference: Optional[str] = None
    sort_by: Optional[str] = None
    sort_order: Optional[str] = None

    # ── 独立偏好字段 ──
    no_agent_fee: Optional[bool] = None
    payment_method: Optional[str] = None
    deposit_type: Optional[str] = None

    # ── 硬约束标签类（直接参数，过滤时匹配房源 tags）──
    pet_policy: Optional[str] = None
    viewing_method: Optional[str] = None
    viewing_time: Optional[str] = None
    lease_flexibility: Optional[str] = None
    required_utilities: Optional[list[str]] = None
    termination_sublet: Optional[str] = None
    parking_type: Optional[str] = None
    security_requirement: Optional[str] = None
    property_management: Optional[str] = None
    environment_preference: Optional[str] = None
    required_nearby: Optional[list[str]] = None
    house_feature: Optional[str] = None
    landlord_contract: Optional[str] = None

    # ── 软约束标识（字段名列表，列表中的字段按软约束处理：匹配加分，不匹配不排除）──
    soft_constraint_keys: list[str] = []

    # ── 上下文记忆 ──
    mentioned_house_ids: list[str] = []
    current_focus_house_id: Optional[str] = None


def build_area_district_map(all_houses: list[dict]) -> dict[str, str]:
    """从全量房源数据中构建 area → district 映射表，跳过 area/district 为空的记录。"""
    mapping: dict[str, str] = {}
    for house in all_houses:
        area = house.get("area")
        district = house.get("district")
        if area and district:
            mapping[area] = district
    return mapping


def build_landmark_names(landmarks: list[dict]) -> set[str]:
    """从地标列表中提取 name 字段，构建用于反向子串匹配的地标名称集合。"""
    return {lm["name"] for lm in landmarks if lm.get("name")}


_LOCATION_FUZZY_SUFFIXES = ("商圈", "商业区", "片区", "附近")










async def update_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
    **kwargs,
) -> dict:
    """提取并合并用户租房偏好到 session，不执行搜索。调用后需再调用 search_by_preferences 获取匹配房源。（实现待重写）"""
    return {
        "preferences_summary": session_prefs.model_dump(
            exclude_none=True, exclude={"clear_location"}
        ),
    }


async def search_by_preferences(
    client: httpx.AsyncClient,
    session_prefs: UserPreferences,
) -> dict:
    """按当前 session 偏好搜索并返回 top 5 精简房源列表。需在 update_preferences 之后调用。（实现待重写）"""
    return {
        "total_matched": 0,
        "total_raw": 0,
        "items": [],
        "preferences_summary": session_prefs.model_dump(
            exclude_none=True, exclude={"clear_location"}
        ),
    }


# ── Story 8.1: 5 工具体系 TOOLS 列表（意图接口 v2）────────────────────────────────
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "提取或更新用户的租房偏好，仅合并偏好不搜索。调用后必须再调用 search_by_preferences 获取匹配房源。每轮只传本轮新增/变更的字段；用户说「最好/希望」时，除设主字段外必须同时设对应 xxx_is_soft: true。数组类（如 required_nearby）追加时只传本轮新增项。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户提到的位置，行政区/商圈/地标/地铁站/小区名均可。示例：[\"海淀\"]、[\"望京\"]、[\"国贸附近\"]、[\"百子湾\"]、[\"西二旗站\"]、[\"建清园南区\"]。多位置用数组：[\"朝阳\",\"海淀\"]"
                    },
                    "clear_location": {
                        "type": "boolean",
                        "description": "true=清除之前的位置（用于「换XX看看」「改到XX」场景），默认 false"
                    },
                    "min_price": {
                        "type": "integer",
                        "description": "最低月租金（元）。「3000以上」→ min_price=3000"
                    },
                    "max_price": {
                        "type": "integer",
                        "description": "最高月租金（元）。「预算5000」「5000以内」→ max_price=5000；「3000左右」→ min_price=2500, max_price=3500"
                    },
                    "bedrooms": {
                        "type": "string",
                        "description": "卧室数，字符串格式。「两居室」→\"2\"，「两居或三居」→\"2,3\"，「一居」→\"1\"。合租单间也传\"1\""
                    },
                    "rental_type": {
                        "type": "string",
                        "enum": ["整租", "合租"],
                        "description": "整租或合租。「一个人住/自己住」→整租；「合租/找室友/有室友」→合租；「单间」→合租"
                    },
                    "decoration": {
                        "type": "string",
                        "enum": ["精装", "简装", "豪华", "毛坯", "空房"],
                        "description": "装修类型。「精装修/精装」→精装，「空房/自己带家具」→空房，「毛坯」→毛坯"
                    },
                    "elevator": {
                        "type": "boolean",
                        "description": "是否要求有电梯。「有电梯/要电梯/老人腿脚不便」→true"
                    },
                    "orientation": {
                        "type": "string",
                        "enum": ["朝南", "朝北", "朝东", "朝西", "南北", "东西", "西北"],
                        "description": "朝向。「朝南/采光好」→朝南，「南北通透」→南北，「西北」→西北"
                    },
                    "floor_pref": {
                        "type": "string",
                        "enum": ["低层", "中层", "高层"],
                        "description": "楼层偏好。「低楼层/一楼」→低层，「高层/视野好」→高层"
                    },
                    "min_area": {
                        "type": "integer",
                        "description": "最小面积（㎡）。「60平以上」→60"
                    },
                    "max_area": {
                        "type": "integer",
                        "description": "最大面积（㎡）"
                    },
                    "max_subway_dist": {
                        "type": "integer",
                        "description": "到最近地铁站最大距离（米）。「近地铁/交通方便」→800；「地铁500米内」→500；「地铁1公里」→1000；「走路10分钟」→800"
                    },
                    "subway_line": {
                        "type": "string",
                        "description": "地铁线路，使用包含匹配（如「13号线」也会匹配「13号线/昌平线」换乘站）。「13号线沿线」→\"13号线\""
                    },
                    "utilities_type": {
                        "type": "string",
                        "enum": ["民水民电", "商水商电"],
                        "description": "水电类型"
                    },
                    "property_type": {
                        "type": "string",
                        "enum": ["住宅", "公寓"],
                        "description": "物业类型"
                    },
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "指定挂牌平台。用户说「在链家上找」→\"链家\""
                    },
                    "available_before": {
                        "type": "string",
                        "description": "可入住日期上限，YYYY-MM-DD。「3月份入住」→\"2026-03-01\"；「3月10号前入住」→\"2026-03-10\""
                    },
                    "max_commute_minutes": {
                        "type": "integer",
                        "description": "到西二旗通勤上限（分钟）。「通勤30分钟内」→30"
                    },
                    "noise_preference": {
                        "type": "string",
                        "enum": ["安静"],
                        "description": "噪音偏好。「安静/不要吵/隔音好/睡眠浅/需要静养/睡眠不好/要安静」→必须设\"安静\""
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["price", "area", "subway"],
                        "description": "排序字段。「按价格排」→price，「按面积排」→area，「按地铁距离排」→subway"
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "排序方向。「从低到高/从近到远/从便宜到贵」→asc，「从高到低/从大到小」→desc"
                    },
                    "no_agent_fee": {
                        "type": "boolean",
                        "description": "true=用户要求免中介费/不想交中介费/房东直租。false 不传"
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["月付", "季付", "半年付", "年付"],
                        "description": "付款周期偏好。「月付/按月付/能不能月付/希望月付」→月付；「季付」→季付。用户问付款方式、月付时用本字段，不要用 lease_flexibility（租期长短）。与 xxx_is_soft 成对使用时可表示「最好能月付」"
                    },
                    "deposit_type": {
                        "type": "string",
                        "enum": ["押一", "押二", "押三"],
                        "description": "押金偏好。「押一付一」→押一，「可以押二」→押二"
                    },
                    "pet_policy": {
                        "type": "string",
                        "enum": ["可养猫", "可养狗", "可养宠物", "不可养宠物", "仅限小型犬", "可养宠物需宠物押金"],
                        "description": "宠物政策（硬约束）。「要能养猫」→可养猫，「能养狗」→可养狗"
                    },
                    "viewing_method": {
                        "type": "string",
                        "enum": ["仅线下看房", "仅线上VR看房", "仅线上AR看房", "仅线上图片看房", "线下+线上"],
                        "description": "看房方式（硬约束）"
                    },
                    "viewing_time": {
                        "type": "string",
                        "enum": ["全天可看房", "仅周末看房", "仅工作日看房", "工作日9-18点", "工作日14-18点", "工作日9-12点", "周末9-18点", "周末14-18点", "周末9-12点"],
                        "description": "看房时间（硬约束）"
                    },
                    "lease_flexibility": {
                        "type": "string",
                        "enum": ["可月租", "可租2个月", "可租3个月", "可租4个月", "可租5个月", "可半年租", "可年租", "仅接受年租"],
                        "description": "租期长短灵活性（硬约束）。「可短租/可月租/最多租3个月」→可月租/可租3个月等。与付款周期 payment_method（月付/季付）区分：用户说「月付」时用 payment_method，不要用本字段"
                    },
                    "required_utilities": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["包水电费", "免水电费", "免宽带费", "包宽带", "包物业费", "免物业费", "包车位", "免车位费", "包取暖费", "免取暖费"]},
                        "description": "必须包含的费用项（硬约束，房源 tags 须全部匹配）。「网费/宽带包含在房租里」→[\"包宽带\"]；「物业费包在房租里」→[\"包物业费\"]；「车位费包含/免费车位」→[\"免车位费\"]。注意：「包」表示含在租金内，「免」表示不另收费；用户说包含在房租里时用「包宽带」「包物业费」，不要用免宽带费/免物业费"
                    },
                    "termination_sublet": {
                        "type": "string",
                        "enum": ["提前退租可协商", "提前退租扣押金", "经同意可转租", "不可转租"],
                        "description": "退租/转租政策（硬约束）"
                    },
                    "parking_type": {
                        "type": "string",
                        "enum": ["车库车位", "露天车位", "无车位"],
                        "description": "车位有无及类型（硬约束）。仅表示要车库/露天/无车位。若用户说「有车位且最好免费」「车位费包在房租里」应用 required_utilities: [\"免车位费\"] 并设 required_utilities_is_soft，不要用本字段"
                    },
                    "security_requirement": {
                        "type": "string",
                        "enum": ["24小时保安", "门禁刷卡", "门禁形同虚设", "无门禁"],
                        "description": "安保/门禁要求（硬约束）"
                    },
                    "property_management": {
                        "type": "string",
                        "enum": ["物业管理到位", "物业管理差"],
                        "description": "物业管理要求（硬约束）"
                    },
                    "environment_preference": {
                        "type": "string",
                        "enum": ["绿化好环境佳", "绿化少环境一般"],
                        "description": "小区环境偏好（硬约束）"
                    },
                    "required_nearby": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["近公园", "近学校", "近菜市场", "近银行", "近医院", "近餐饮", "近健身房", "近警察局", "近商超", "近加油站"]},
                        "description": "必须有的周边配套（硬约束，房源 tags 须全部匹配）"
                    },
                    "house_feature": {
                        "type": "string",
                        "enum": ["采光好", "南北通透", "高性价比"],
                        "description": "房屋特点（硬约束）"
                    },
                    "landlord_contract": {
                        "type": "string",
                        "enum": ["合同规范条款清晰", "合同不规范", "房东好沟通", "房东不配合", "房东难联系"],
                        "description": "合同/房东相关要求（硬约束）"
                    },
                    "decoration_is_soft": {"type": "boolean", "description": "true=本轮回该维度为软约束（匹配加分，不匹配不排除）。仅当用户说「最好/希望/如果有」时设为 true"},
                    "elevator_is_soft": {"type": "boolean", "description": "同上，对应 elevator"},
                    "orientation_is_soft": {"type": "boolean", "description": "同上，对应 orientation"},
                    "floor_pref_is_soft": {"type": "boolean", "description": "同上，对应 floor_pref"},
                    "max_subway_dist_is_soft": {"type": "boolean", "description": "同上，对应 max_subway_dist"},
                    "rental_type_is_soft": {"type": "boolean", "description": "同上，对应 rental_type"},
                    "pet_policy_is_soft": {"type": "boolean", "description": "同上，对应 pet_policy"},
                    "viewing_method_is_soft": {"type": "boolean", "description": "同上，对应 viewing_method"},
                    "viewing_time_is_soft": {"type": "boolean", "description": "同上，对应 viewing_time"},
                    "lease_flexibility_is_soft": {"type": "boolean", "description": "同上，对应 lease_flexibility"},
                    "termination_sublet_is_soft": {"type": "boolean", "description": "同上，对应 termination_sublet"},
                    "parking_type_is_soft": {"type": "boolean", "description": "同上，对应 parking_type"},
                    "security_requirement_is_soft": {"type": "boolean", "description": "同上，对应 security_requirement"},
                    "property_management_is_soft": {"type": "boolean", "description": "同上，对应 property_management"},
                    "environment_preference_is_soft": {"type": "boolean", "description": "同上，对应 environment_preference"},
                    "house_feature_is_soft": {"type": "boolean", "description": "同上，对应 house_feature"},
                    "landlord_contract_is_soft": {"type": "boolean", "description": "同上，对应 landlord_contract"},
                    "required_utilities_is_soft": {"type": "boolean", "description": "同上，对应 required_utilities"},
                    "required_nearby_is_soft": {"type": "boolean", "description": "同上，对应 required_nearby"},
                    "payment_method_is_soft": {"type": "boolean", "description": "同上，对应 payment_method"},
                    "deposit_type_is_soft": {"type": "boolean", "description": "同上，对应 deposit_type"},
                    "no_agent_fee_is_soft": {"type": "boolean", "description": "同上，对应 no_agent_fee"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_preferences",
            "description": "按当前已合并的偏好搜索房源，返回匹配的 top 5 精简列表。必须在 update_preferences 之后调用。当用户说「帮我找找」「找一下」等明确找房意图时，若本轮有新增偏好须先 update_preferences 再调用本工具；若偏好已在之前轮次设置且本轮仅表达找房意图，可直接调用本工具。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_detail",
            "description": "获取单套房源完整详情：地址、户型、面积、租金、装修、朝向、楼层、设施、噪音评级、标签等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源 ID，格式如 HF_1、HF_25"}
                },
                "required": ["house_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_house_listings",
            "description": "获取指定房源在链家/安居客/58同城三个平台的全部挂牌记录，用于比较同一房源的跨平台价格差异。",
            "parameters": {
                "type": "object",
                "properties": {
                    "house_id": {"type": "string", "description": "房源 ID，如 HF_1"}
                },
                "required": ["house_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_action",
            "description": "对指定房源执行租房、退租或下架操作，调用 API 完成状态变更（不能只回复文字，必须调用此工具）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["rent", "terminate", "offline"],
                        "description": "rent=租房，terminate=退租，offline=下架"
                    },
                    "house_id": {"type": "string", "description": "房源 ID，格式如 HF_1"},
                    "listing_platform": {
                        "type": "string",
                        "enum": ["链家", "安居客", "58同城"],
                        "description": "挂牌平台，必填"
                    }
                },
                "required": ["action", "house_id", "listing_platform"]
            }
        }
    }
]


# ── Task 2: search_houses ───────────────────────────────────────────────────
async def search_houses(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        base_params: dict = {k: v for k, v in kwargs.items() if v is not None}
        base_params["page"] = 1

        resp = await client.get(
            "/api/houses/by_platform",
            params=base_params,
            headers=_get_headers(),
        )
        resp.raise_for_status()

        result = resp.json()
        inner = result.get("data", result)
        all_items: list = list(inner.get("items", []))
        total: int = inner.get("total", len(all_items))

        page = 2
        while len(all_items) < total:
            next_params = {**base_params, "page": page}
            next_resp = await client.get(
                "/api/houses/by_platform",
                params=next_params,
                headers=_get_headers(),
            )
            next_resp.raise_for_status()
            next_result = next_resp.json()
            next_inner = next_result.get("data", next_result)
            all_items.extend(next_inner.get("items", []))
            page += 1

        return {"total": total, "items": all_items}
    except Exception as e:
        return {"error": f"search_houses failed: {str(e)}"}


# ── Task 3: get_house_detail ────────────────────────────────────────────────
async def get_house_detail(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        resp = await client.get(f"/api/houses/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_house_detail failed: {str(e)}"}


# ── Task 4: search_landmark ─────────────────────────────────────────────────
async def search_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {}
        # TOOLS schema 用 "query"，API 实际参数名为 "q"
        if kwargs.get("query") is not None:
            params["q"] = kwargs["query"]
        if kwargs.get("category") is not None:
            params["category"] = kwargs["category"]
        if kwargs.get("district") is not None:
            params["district"] = kwargs["district"]

        # 地标接口不需要 X-User-ID
        resp = await client.get("/api/landmarks/search", params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"search_landmark failed: {str(e)}"}


# ── Task 5: search_nearby_landmark ─────────────────────────────────────────
async def search_nearby_landmark(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        resp = await client.get(
            "/api/houses/nearby",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"search_nearby_landmark failed: {str(e)}"}


# ── Task 6: get_nearby_amenities ────────────────────────────────────────────
async def get_nearby_amenities(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        # FR16 要求 1000 米，覆盖 API 默认的 3000 米
        if "max_distance_m" not in params:
            params["max_distance_m"] = 1000
        resp = await client.get(
            "/api/houses/nearby_landmarks",
            params=params,
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_nearby_amenities failed: {str(e)}"}


# ── Task 7: execute_action ──────────────────────────────────────────────────
async def execute_action(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        action = kwargs.get("action", "")
        house_id = str(kwargs.get("house_id", ""))
        listing_platform = kwargs.get("listing_platform", "安居客")

        valid_actions = {"rent", "terminate", "offline"}
        if action not in valid_actions:
            return {"error": f"execute_action failed: unknown action {action}"}

        resp = await client.post(
            f"/api/houses/{house_id}/{action}",
            params={"listing_platform": listing_platform},
            headers=_get_headers(),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"execute_action failed: {str(e)}"}


# ── get_houses_by_community ─────────────────────────────────────────────────
async def get_houses_by_community(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        params: dict = {k: v for k, v in kwargs.items() if v is not None}
        resp = await client.get("/api/houses/by_community", params=params, headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_houses_by_community failed: {str(e)}"}


# ── get_house_listings ───────────────────────────────────────────────────────
async def get_house_listings(client: httpx.AsyncClient, **kwargs) -> dict:
    try:
        house_id = str(kwargs.get("house_id", ""))
        resp = await client.get(f"/api/houses/listings/{house_id}", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"get_house_listings failed: {str(e)}"}


# ── get_all_houses_for_debug：session 初始化时获取全量房屋用于调试 ───────
PLATFORMS = ["链家", "安居客", "58同城"]


async def _fetch_all_houses_for_platform(
    client: httpx.AsyncClient, platform: str
) -> dict:
    """不受 MAX_PAGES 限制地翻页，获取单个平台的全量房源。"""
    all_items: list = []
    page = 1
    page_size = 200
    total = None
    while True:
        try:
            resp = await client.get(
                "/api/houses/by_platform",
                params={
                    "page": page,
                    "page_size": page_size,
                    "listing_platform": platform,
                },
                headers=_get_headers(),
            )
            resp.raise_for_status()
        except Exception:
            break
        inner = resp.json().get("data", resp.json())
        items = inner.get("items", [])
        if total is None:
            total = inner.get("total", 0)
        all_items.extend(items)
        if not items or len(all_items) >= total:
            break
        page += 1
    return {"total": total or len(all_items), "items": all_items}


async def get_all_houses_for_debug(client: httpx.AsyncClient) -> dict:
    """获取链家、安居客、58同城三个平台的全量房源，用于调试日志。"""
    tasks = [
        _fetch_all_houses_for_platform(client, platform) for platform in PLATFORMS
    ]
    results = await asyncio.gather(*tasks)
    return {platform: result for platform, result in zip(PLATFORMS, results)}


# ── get_all_landmarks_for_debug：session 初始化时获取全量地标用于调试 ──────
async def get_all_landmarks_for_debug(client: httpx.AsyncClient) -> dict:
    """获取全量地标数据用于调试日志。"""
    try:
        resp = await client.get("/api/landmarks")
        resp.raise_for_status()
        inner = resp.json().get("data", resp.json())
        items = inner.get("items", [])
        return {"total": len(items), "items": items}
    except Exception as e:
        return {"error": f"get_all_landmarks_for_debug failed: {str(e)}", "total": 0, "items": []}


# ── init_houses（Story 2.2 已实现，保持不变） ───────────────────────────────
async def init_houses(client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.post("/api/houses/init", headers=_get_headers())
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"init_houses failed: {str(e)}"}
