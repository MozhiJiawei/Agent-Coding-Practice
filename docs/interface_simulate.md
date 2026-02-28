# 租房仿真 API 使用指导

本文档主要说明如何正确使用比赛环境中的租房仿真 API，包括房源概况、可用接口列表以及使用时需要遵从的一些硬性要求。

---

## 一、房源情况介绍

### 数据规模

- **覆盖区域**：北京行政区（如 海淀、朝阳、通州、昌平、大兴、房山、西城、丰台、顺义、东城）
- **价格区间**：约 500–25000 元/月
- **支持查询**：价格、户型、区域、地铁距离、附近地标、可入住日期、西二旗通勤时间等维度
- **地标数据**：地铁站、世界 500 强企业、商圈地标（含商超/公园）

### 数据源说明

#### 1. 房源基础信息

覆盖地址、户型、面积、租金、可入住日期与楼层，可按行政区与商圈检索。

- **地址**：北京行政区，房源落在地铁站、商圈、世界 500 强企业所在地标周边，小区名与商圈具体名称由地标决定（例如西二旗、国贸、望京）。
- **户型**：整租与合租约各占 50%；整租为一居至四居多种室厅卫组合，面积约 22～145 ㎡；合租为单间，整套为 2 室、3 室或 4 室一厅一卫或两卫，单间面积约 12～30 ㎡，月租约 1200～3500 元。
- **租金**：整租月租约 800～28000 元/月，付款单位元/月。

#### 2. 通勤信息

每条房源均带地铁与到西二旗通勤信息，支持按商圈、地铁距离、通勤时间筛选。

- 最近地铁站及距地铁站距离约 200～5500 米分段覆盖。
- 到西二旗通勤时间约 8～95 分钟。

#### 3. 配置信息

仅覆盖周边生活配套中的商超与公园。

- 可查房源周边商超、公园及距离。

#### 4. 房屋设施

含电梯、装修、朝向、卫生间（室厅卫中的几卫）。

- **装修**：简装、精装、豪华、毛坯、空房。
- **朝向**：朝南、朝北、朝东、朝西、南北、东西。
- **卫生间**：以室、厅、卫中的「几卫」体现（如一卫、双卫）。

#### 5. 房源隐形信息

含噪音水平、标签与房源状态，用于表达「近地铁但临街略吵」、采光等潜在信息。

- **噪音水平**：安静、中等、吵闹、临街。
- **标签**：近地铁、双地铁、多地铁；精装修、豪华装修、毛坯、空房；朝南、南北通透、采光好；有电梯、高楼层、高层；小户型、大户型、大两居、大三居、双卫；核心区、学区房、近高校；合租、小单间、商住；低价、高性价比、农村房、农村自建房；部分商圈或路名。
- **房源状态**：可租、已租、下架（约 90%、5%、5%）。

---

## 二、使用接口的硬性要求

### 请求头

- 房源相关接口（`/api/houses/*`）必须带请求头 `X-User-ID`，否则返回 `400`。
- 地标接口（`/api/landmarks/*`）不需要 `X-User-ID`。
- `X-User-ID` 的值即为用户工号，注意**必须传比赛平台注册的用户工号**，比赛的用例会按照用户工号隔离，若传值有误用例执行结果会有冲突影响成绩！

### 房源数据重置

用例执行过程中会改变房源的状态（可租/已租/下架），重复执行同一个用例时，由于数据状态发生改变会导致执行失败，因此建议在 Agent 中定义每新起一个 Session，就去调用房源数据重置接口，保障每次用例执行都能够使用初始化的数据。

**房源数据重置接口**

```bash
curl -s -X POST -H "X-User-ID: 真实工号" "http://7.225.29.223:8080/api/houses/init"
```

成功响应示例：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "action": "reset_user",
    "message": "该用户状态覆盖已清空，房源恢复为初始状态",
    "user_id": "真实工号"
  }
}
```

> **注**：自动判题在每个用例执行前会自动进行房源数据初始化。

### 租房/退租/下架操作

必须调用对应 API 才算完成操作，仅在对话中生成 `[已租]` 无效。

### 近距离概念说明

- **近地铁**：指房源到最近地铁站的直线距离。接口返回字段为 `subway_distance`（单位：米）。筛选时用参数 `max_subway_dist`：800 米以内视为近地铁，1000 米以内视为地铁可达。
- **地标附近房源（接口 9）**：以地标为圆心，按直线距离（米）筛选，参数 `max_distance` 默认 2000。返回结果中同时给出 `distance_to_landmark`（直线距离）、`walking_distance`（估算步行距离）、`walking_duration`（估算步行时间，分钟）。
- **小区周边地标（接口 10）**：以该小区为基准点，按直线距离（米）筛选，参数 `max_distance_m` 默认 3000，用于查商超、公园等周边配套。

---

## 三、可用接口列表

| 序号 | 方法 | 路径 | 描述 |
|------|------|------|------|
| 1 | `GET` | `/api/landmarks` | 获取地标列表，支持 `category`、`district` 同时筛选（取交集）。用于查地铁站、公司、商圈等地标。不需 `X-User-ID`。 |
| 2 | `GET` | `/api/landmarks/name/{name}` | 按名称精确查询地标，如西二旗站、百度。返回地标 id、经纬度等，用于后续 nearby 查房。不需 `X-User-ID`。 |
| 3 | `GET` | `/api/landmarks/search` | 关键词模糊搜索地标，`q` 必填。支持 `category`、`district` 同时筛选，多条件取交集。不需 `X-User-ID`。 |
| 4 | `GET` | `/api/landmarks/{id}` | 按地标 id 查询地标详情。不需 `X-User-ID`。 |
| 5 | `GET` | `/api/landmarks/stats` | 获取地标统计信息（总数、按类别分布等）。不需 `X-User-ID`。 |
| 6 | `GET` | `/api/houses/{house_id}` | 根据房源 ID 获取单套房源详情。无 query 参数，仅路径带 `house_id`，返回一条（安居客），便于智能体解析。调用时请求头必带 `X-User-ID`。 |
| 7 | `GET` | `/api/houses/listings/{house_id}` | 根据房源 ID 获取该房源在链家/安居客/58同城等各平台的全部挂牌记录。无 query 参数。调用时请求头必带 `X-User-ID`。响应 `data` 为 `{ total, page_size, items }`。 |
| 8 | `GET` | `/api/houses/by_community` | 按小区名查询该小区下可租房源。默认每页 10 条、未传 `listing_platform` 时只返回安居客。用于指代消解、查某小区地铁信息或隐性属性。调用时请求头必带 `X-User-ID`。 |
| 9 | `GET` | `/api/houses/by_platform` | 查询可租房源，支持按挂牌平台筛选。`listing_platform` 可选：不传则默认使用安居客；传 链家/安居客/58同城 则只返回该平台。其他参数同 `GET /api/houses`。调用时请求头必带 `X-User-ID`。 |
| 10 | `GET` | `/api/houses/nearby` | 以地标为圆心，查询在指定距离内的可租房源，返回带直线距离、步行距离、步行时间。默认每页 10 条、未传 `listing_platform` 时只返回安居客。需先通过地标接口获得 `landmark_id`。调用时请求头必带 `X-User-ID`。 |
| 11 | `GET` | `/api/houses/nearby_landmarks` | 查询某小区周边某类地标（商超/公园），按距离排序。用于回答「附近有没有商场/公园」。调用时请求头必带 `X-User-ID`。 |
| 12 | `GET` | `/api/houses/stats` | 获取房源统计信息（总套数、按状态/行政区/户型分布、价格区间等），按当前用户视角统计。调用时请求头必带 `X-User-ID`。 |
| 13 | `POST` | `/api/houses/{house_id}/rent` | 将当前用户视角下该房源设为已租。传入房源 ID 与 `listing_platform`（必填，链家/安居客/58同城）以明确租赁哪个平台；三平台状态一并更新，响应返回该条。调用时请求头必带 `X-User-ID`。 |
| 14 | `POST` | `/api/houses/{house_id}/terminate` | 将当前用户视角下该房源恢复为可租。传入房源 ID 与 `listing_platform`（必填）以明确操作哪个平台；三平台状态一并更新，响应返回该条。调用时请求头必带 `X-User-ID`。 |
| 15 | `POST` | `/api/houses/{house_id}/offline` | 将当前用户视角下该房源设为下架。传入房源 ID 与 `listing_platform`（必填）以明确操作哪个平台；三平台状态一并更新，响应返回该条。调用时请求头必带 `X-User-ID`。 |

> 接口实现详情见附件。

---

## FAQ

**Q：重复执行同一个用例，第二次执行后房源数据查询不到了**

A：首次执行用例时，将房源数据状态更新为了已租，再次执行用例查询可租房源时返回结果必然为空。此时可以手动触发房源重置接口（见第二章节）。


# 接口详细说明

```
{
    "openapi": "3.0.3",
    "info": {
        "title": "Fake App Agent API",
        "version": "1.0.0",
        "description": "租房仿真与评测用 API，地标与房源查询、租房/退租/下架等"
    },
    "servers": [
        {
            "url": "http://7.225.29.223:8080",
            "description": "租房仿真服务"
        }
    ],
    "paths": {
        "/api/landmarks": {
            "get": {
                "operationId": "get_landmarks",
                "summary": "获取地标列表",
                "description": "获取地标列表，支持 category、district 同时筛选（取交集）。用于查地铁站、公司、商圈等地标。不需 X-User-ID。",
                "parameters": [
                    {
                        "name": "category",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "地标类别：subway(地铁)/company(公司)/landmark(商圈等)，不传则不过滤"
                        }
                    },
                    {
                        "name": "district",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "行政区，如 海淀、朝阳"
                        }
                    }
                ]
            }
        },
        "/api/landmarks/name/{name}": {
            "get": {
                "operationId": "get_landmark_by_name",
                "summary": "按名称精确查询地标",
                "description": "按名称精确查询地标，如西二旗站、百度。返回地标 id、经纬度等，用于后续 nearby 查房。不需 X-User-ID。",
                "parameters": [
                    {
                        "name": "name",
                        "in": "path",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "地标名称，如 西二旗站、国贸"
                        }
                    }
                ]
            }
        },
        "/api/landmarks/search": {
            "get": {
                "operationId": "search_landmarks",
                "summary": "关键词模糊搜索地标",
                "description": "关键词模糊搜索地标，q即地标名比如西二旗。支持 category、district 同时筛选，多条件取交集。不需 X-User-ID。",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "搜索关键词，必填"
                        }
                    },
                    {
                        "name": "category",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "可选，限定类别：subway/company/landmark"
                        }
                    },
                    {
                        "name": "district",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "可选，限定行政区，如 海淀、朝阳"
                        }
                    }
                ]
            }
        },
        "/api/landmarks/{id}": {
            "get": {
                "operationId": "get_landmark_by_id",
                "summary": "按地标 id 查询地标详情",
                "description": "按地标 id 查询地标详情。不需 X-User-ID。",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "地标 ID，如 SS_001、LM_002"
                        }
                    }
                ]
            }
        },
        "/api/landmarks/stats": {
            "get": {
                "operationId": "get_landmark_stats",
                "summary": "获取地标统计信息",
                "description": "获取地标统计信息（总数、按类别分布等）。不需 X-User-ID。",
                "parameters": []
            }
        },
        "/api/houses/{house_id}": {
            "get": {
                "operationId": "get_house_by_id",
                "summary": "根据房源 ID 获取详情",
                "description": "根据房源 ID 获取单套房源详情。无 query 参数，仅路径带 house_id，返回一条（安居客），便于智能体解析。调用时请求头必带 X-User-ID。",
                "parameters": [
                    {
                        "name": "house_id",
                        "in": "path",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "房源 ID，如 HF_2001"
                        }
                    }
                ]
            }
        },
        "/api/houses/listings/{house_id}": {
            "get": {
                "operationId": "get_house_listings",
                "summary": "根据房源 ID 获取各平台挂牌记录",
                "description": "根据房源 ID 获取该房源在链家/安居客/58同城等各平台的全部挂牌记录。无 query 参数。调用时请求头必带 X-User-ID。响应 data 为 { total, page_size, items }。",
                "parameters": [
                    {
                        "name": "house_id",
                        "in": "path",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "房源 ID，如 HF_2001"
                        }
                    }
                ]
            }
        },
        "/api/houses/by_community": {
            "get": {
                "operationId": "get_houses_by_community",
                "summary": "按小区名查询可租房源",
                "description": "按小区名查询该小区下可租房源。默认每页 10 条、未传 listing_platform 时只返回安居客。用于指代消解、查某小区地铁信息或隐性属性。调用时请求头必带 X-User-ID。",
                "parameters": [
                    {
                        "name": "community",
                        "in": "query",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "小区名，与数据一致，如 建清园(南区)、保利锦上(二期)"
                        }
                    },
                    {
                        "name": "listing_platform",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "enum": [
                                "链家",
                                "安居客",
                                "58同城"
                            ],
                            "description": "挂牌平台，不传则默认安居客"
                        }
                    },
                    {
                        "name": "page",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "页码，默认 1"
                        }
                    },
                    {
                        "name": "page_size",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "每页条数，默认 10，最大 10000"
                        }
                    }
                ]
            }
        },
        "/api/houses/by_platform": {
            "get": {
                "operationId": "get_houses_by_platform",
                "summary": "按挂牌平台筛选房源（平台可选）",
                "description": "查询可租房源，支持按挂牌平台筛选。listing_platform 可选：不传则默认使用安居客；传 链家/安居客/58同城 则只返回该平台。其他参数同 GET /api/houses。调用时请求头必带 X-User-ID。",
                "parameters": [
                    {
                        "name": "listing_platform",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "enum": [
                                "链家",
                                "安居客",
                                "58同城"
                            ],
                            "description": "挂牌平台，可选。不传则默认安居客；传则仅返回该平台"
                        }
                    },
                    {
                        "name": "district",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "行政区，逗号分隔，如 海淀,朝阳"
                        }
                    },
                    {
                        "name": "area",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "商圈，逗号分隔，如 西二旗,上地"
                        }
                    },
                    {
                        "name": "min_price",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "最低月租金（元）"
                        }
                    },
                    {
                        "name": "max_price",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "最高月租金（元）"
                        }
                    },
                    {
                        "name": "bedrooms",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "卧室数，逗号分隔，如 1,2"
                        }
                    },
                    {
                        "name": "rental_type",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "整租 或 合租"
                        }
                    },
                    {
                        "name": "decoration",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "精装/简装 等"
                        }
                    },
                    {
                        "name": "orientation",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "朝向，如 朝南、南北"
                        }
                    },
                    {
                        "name": "elevator",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "是否有电梯：true/false"
                        }
                    },
                    {
                        "name": "min_area",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "最小面积（平米）"
                        }
                    },
                    {
                        "name": "max_area",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "最大面积（平米）"
                        }
                    },
                    {
                        "name": "property_type",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "物业类型，如 住宅"
                        }
                    },
                    {
                        "name": "subway_line",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "地铁线路，如 13号线"
                        }
                    },
                    {
                        "name": "max_subway_dist",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "最大地铁距离（米），近地铁建议 800"
                        }
                    },
                    {
                        "name": "subway_station",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "地铁站名，如 车公庄站"
                        }
                    },
                    {
                        "name": "utilities_type",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "水电类型，如 民水民电"
                        }
                    },
                    {
                        "name": "available_from_before",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "可入住日期上限，YYYY-MM-DD（如 2026-03-10）"
                        }
                    },
                    {
                        "name": "commute_to_xierqi_max",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "到西二旗通勤时间上限（分钟）"
                        }
                    },
                    {
                        "name": "sort_by",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "排序字段：price/area/subway"
                        }
                    },
                    {
                        "name": "sort_order",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "asc 或 desc"
                        }
                    },
                    {
                        "name": "page",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "页码，默认 1"
                        }
                    },
                    {
                        "name": "page_size",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "每页条数，默认 10，最大 10000"
                        }
                    }
                ]
            }
        },
        "/api/houses/nearby_landmarks": {
            "get": {
                "operationId": "get_nearby_landmarks",
                "summary": "查询小区周边地标",
                "description": "查询某小区周边某类地标（商超/公园），按距离排序。用于回答「附近有没有商场/公园」。调用时请求头必带 X-User-ID。",
                "parameters": [
                    {
                        "name": "community",
                        "in": "query",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "小区名，用于定位基准点"
                        }
                    },
                    {
                        "name": "type",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "description": "地标类型：shopping(商超) 或 park(公园)，不传则不过滤"
                        }
                    },
                    {
                        "name": "max_distance_m",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "number",
                            "description": "最大距离（米），默认 3000"
                        }
                    }
                ]
            }
        },
        "/api/houses/nearby": {
            "get": {
                "operationId": "get_houses_nearby",
                "summary": "以地标为圆心查附近房源",
                "description": "以地标为圆心，查询在指定距离内的可租房源，返回带直线距离、步行距离、步行时间。默认每页 10 条、未传 listing_platform 时只返回安居客。需先通过地标接口获得 landmark_id。调用时请求头必带 X-User-ID。",
                "parameters": [
                    {
                        "name": "landmark_id",
                        "in": "query",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "地标 ID 或地标名称（支持按名称查找）"
                        }
                    },
                    {
                        "name": "max_distance",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "number",
                            "description": "最大直线距离（米），默认 2000"
                        }
                    },
                    {
                        "name": "listing_platform",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "string",
                            "enum": [
                                "链家",
                                "安居客",
                                "58同城"
                            ],
                            "description": "挂牌平台，不传则默认安居客"
                        }
                    },
                    {
                        "name": "page",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "页码，默认 1"
                        }
                    },
                    {
                        "name": "page_size",
                        "in": "query",
                        "required": false,
                        "schema": {
                            "type": "integer",
                            "description": "每页条数，默认 10，最大 10000"
                        }
                    }
                ]
            }
        },
        "/api/houses/stats": {
            "get": {
                "operationId": "get_house_stats",
                "summary": "获取房源统计信息",
                "description": "获取房源统计信息（总套数、按状态/行政区/户型分布、价格区间等），按当前用户视角统计。调用时请求头必带 X-User-ID。",
                "parameters": []
            }
        },
        "/api/houses/{house_id}/rent": {
            "post": {
                "operationId": "rent_house",
                "summary": "租房",
                "description": "将当前用户视角下该房源设为已租。传入房源 ID 与 listing_platform（必填，链家/安居客/58同城）以明确租赁哪个平台；三平台状态一并更新，响应返回该条。调用时请求头必带 X-User-ID。",
                "parameters": [
                    {
                        "name": "house_id",
                        "in": "path",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "房源 ID，如 HF_2001"
                        }
                    },
                    {
                        "name": "listing_platform",
                        "in": "query",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "enum": [
                                "链家",
                                "安居客",
                                "58同城"
                            ],
                            "description": "必填。明确租赁哪个平台；三平台状态都会更新，返回该条"
                        }
                    }
                ]
            }
        },
        "/api/houses/{house_id}/terminate": {
            "post": {
                "operationId": "terminate_rental",
                "summary": "退租",
                "description": "将当前用户视角下该房源恢复为可租。传入房源 ID 与 listing_platform（必填）以明确操作哪个平台；三平台状态一并更新，响应返回该条。调用时请求头必带 X-User-ID。",
                "parameters": [
                    {
                        "name": "house_id",
                        "in": "path",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "房源 ID，如 HF_2001"
                        }
                    },
                    {
                        "name": "listing_platform",
                        "in": "query",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "enum": [
                                "链家",
                                "安居客",
                                "58同城"
                            ],
                            "description": "必填。明确操作哪个平台；三平台状态都会更新，返回该条"
                        }
                    }
                ]
            }
        },
        "/api/houses/{house_id}/offline": {
            "post": {
                "operationId": "take_offline",
                "summary": "下架",
                "description": "将当前用户视角下该房源设为下架。传入房源 ID 与 listing_platform（必填）以明确操作哪个平台；三平台状态一并更新，响应返回该条。调用时请求头必带 X-User-ID。",
                "parameters": [
                    {
                        "name": "house_id",
                        "in": "path",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "description": "房源 ID，如 HF_2001"
                        }
                    },
                    {
                        "name": "listing_platform",
                        "in": "query",
                        "required": true,
                        "schema": {
                            "type": "string",
                            "enum": [
                                "链家",
                                "安居客",
                                "58同城"
                            ],
                            "description": "必填。明确操作哪个平台；三平台状态都会更新，返回该条"
                        }
                    }
                ]
            }
        }
    }
}

```

# 接口调用示例

```
你好
{"type": "test_run_start", "base_url": "http://7.225.29.223:8080", "user_id": "l00933108", "timestamp": "2026-02-28T16:33:50.541794"}
{"timestamp": "2026-02-28T16:33:51.143286", "scenario": "1_landmarks_list_noparam", "request": {"method": "GET", "path": "/api/landmarks", "params": {}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"total": 105, "items": [{"id": "SS_021", "name": "国展站", "category": "subway", "district": "顺义", "longitude": 116.5567, "latitude": 40.0583, "details": {"category": "subway", "district": "顺义", "latitude": 40.0583, "lines": ["15号线"], "longitude": 116.5567, "name": "国展站", "station_id": "SS_021", "type": "normal"}}, {"id": "SS_022", "name": "惠新西街南口站", "category": "subway", "district": "朝阳", "longitude": 116.4017, "latitude": 39.9789, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9789, "lines": ["5号线", "10号线"], "longitude": 116.4017, "name": "惠新西街南口站", "station_id": "SS_022", "type": "transfer"}}, {"id": "SS_026", "name": "中关村站", "category": "subway", "district": "海淀", "longitude": 116.3189, "latitude": 39.9856, "details": {"category": "subway", "district": "海淀", "latitude": 39.9856, "lines": ["4号线大兴线"], "longitude": 116.3189, "name": "中关村站", "station_id": "SS_026", "type": "normal"}}, {"id": "SS_039", "name": "六道口站", "category": "subway", "district": "海淀", "longitude": 116.3589, "latitude": 40.0012, "details": {"category": "subway", "district": "海淀", "latitude": 40.0012, "lines": ["15号线", "昌平线"], "longitude": 116.3589, "name": "六道口站", "station_id": "SS_039", "type": "transfer"}}, {"id": "SS_043", "name": "菜市口站", "category": "subway", "district": "西城", "longitude": 116.3812, "latitude": 39.8912, "details": {"category": "subway", "district": "西城", "latitude": 39.8912, "lines": ["4号线大兴线", "7号线"], "longitude": 116.3812, "name": "菜市口站", "station_id": "SS_043", "type": "transfer"}}, {"id": "SS_025", "name": "西直门站", "category": "subway", "district": "西城", "longitude": 116.3612, "latitude": 39.9423, "details": {"category": "subway", "district": "西城", "latitude": 39.9423, "lines": ["2号线", "4号线大兴线", "13号线"], "longitude": 116.3612, "name": "西直门站", "station_id": "SS_025", "type": "transfer"}}, {"id": "SS_033", "name": "西单站", "category": "subway", "district": "西城", "longitude": 116.3812, "latitude": 39.9134, "details": {"category": "subway", "district": "西城", "latitude": 39.9134, "lines": ["1号线", "4号线大兴线"], "longitude": 116.3812, "name": "西单站", "station_id": "SS_033", "type": "transfer"}}, {"id": "SS_034", "name": "复兴门站", "category": "subway", "district": "西城", "longitude": 116.3612, "latitude": 39.9123, "details": {"category": "subway", "district": "西城", "latitude": 39.9123, "lines": ["1号线", "2号线"], "longitude": 116.3612, "name": "复兴门站", "station_id": "SS_034", "type": "transfer"}}, {"id": "F500_005", "name": "中国工商银行", "category": "company", "district": "西城", "longitude": 116.3612, "latitude": 39.9123, "details": {"address": "北京市西城区复兴门内大街55号", "category": "company", "company_id": "F500_005", "district": "西城", "industry": "银行", "latitude": 39.9123, "longitude": 116.3612, "name": "中国工商银行", "name_en": "Industrial and Commercial Bank of China", "nearby_subway": "复兴门站", "rank_2024": 22, "short_name": "工行"}}, {"id": "F500_024", "name": "中粮集团", "category": "company", "district": "朝阳", "longitude": 116.4412, "latitude": 39.9289, "details": {"address": "北京市朝阳区朝阳门南大街8号", "category": "company", "company_id": "F500_024", "district": "朝阳", "industry": "食品", "latitude": 39.9289, "longitude": 116.4412, "name": "中粮集团", "name_en": "COFCO", "nearby_subway": "朝阳门站", "rank_2024": 96, "short_name": "中粮"}}, {"id": "F500_030", "name": "国家能源集团", "category": "company", "district": "东城", "longitude": 116.4312, "latitude": 39.9412, "details": {"address": "北京市东城区东直门南大街3号", "category": "company", "company_id": "F500_030", "district": "东城", "industry": "能源", "latitude": 39.9412, "longitude": 116.4312, "name": "国家能源集团", "name_en": "National Energy Investment", "nearby_subway": "东四十条站", "rank_2024": 84, "short_name": "国能"}}, {"id": "LM_005", "name": "朝阳大悦城", "category": "landmark", "district": "朝阳", "longitude": 116.5212, "latitude": 39.9289, "details": {"address": "北京市朝阳区朝阳北路101号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_005", "latitude": 39.9289, "longitude": 116.5212, "name": "朝阳大悦城", "nearby_subway": "青年路站", "type": "shopping", "type_name": "购物中心"}}, {"id": "SS_004", "name": "大望路站", "category": "subway", "district": "朝阳", "longitude": 116.4789, "latitude": 39.9083, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9083, "lines": ["1号线", "14号线"], "longitude": 116.4789, "name": "大望路站", "station_id": "SS_004", "type": "transfer"}}, {"id": "SS_042", "name": "磁器口站", "category": "subway", "district": "东城", "longitude": 116.4212, "latitude": 39.8912, "details": {"category": "subway", "district": "东城", "latitude": 39.8912, "lines": ["5号线", "7号线"], "longitude": 116.4212, "name": "磁器口站", "station_id": "SS_042", "type": "transfer"}}, {"id": "F500_026", "name": "中铝集团", "category": "company", "district": "西城", "longitude": 116.3589, "latitude": 39.9156, "details": {"address": "北京市西城区金融大街35号", "category": "company", "company_id": "F500_026", "district": "西城", "industry": "金属", "latitude": 39.9156, "longitude": 116.3589, "name": "中铝集团", "name_en": "Aluminum Corp of China", "nearby_subway": "复兴门站", "rank_2024": 142, "short_name": "中铝"}}, {"id": "LM_001", "name": "三里屯太古里", "category": "landmark", "district": "朝阳", "longitude": 116.4567, "latitude": 39.9356, "details": {"address": "北京市朝阳区三里屯路19号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_001", "latitude": 39.9356, "longitude": 116.4567, "name": "三里屯太古里", "nearby_subway": "团结湖站", "type": "shopping", "type_name": "购物中心"}}, {"id": "LM_007", "name": "蓝色港湾", "category": "landmark", "district": "朝阳", "longitude": 116.4812, "latitude": 39.9512, "details": {"address": "北京市朝阳区朝阳公园路6号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_007", "latitude": 39.9512, "longitude": 116.4812, "name": "蓝色港湾", "nearby_subway": "枣营站", "type": "shopping", "type_name": "购物中心"}}, {"id": "LM_023", "name": "国家大剧院", "category": "landmark", "district": "西城", "longitude": 116.3912, "latitude": 39.9089, "details": {"address": "北京市西城区西长安街2号", "category": "landmark", "district": "西城", "landmark_id": "LM_023", "latitude": 39.9089, "longitude": 116.3912, "name": "国家大剧院", "nearby_subway": "天安门西站", "type": "culture", "type_name": "文化"}}, {"id": "SS_006", "name": "十里堡站", "category": "subway", "district": "朝阳", "longitude": 116.5123, "latitude": 39.9289, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9289, "lines": ["6号线"], "longitude": 116.5123, "name": "十里堡站", "station_id": "SS_006", "type": "normal"}}, {"id": "SS_009", "name": "高碑店站", "category": "subway", "district": "朝阳", "longitude": 116.5439, "latitude": 39.9067, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9067, "lines": ["八通线"], "longitude": 116.5439, "name": "高碑店站", "station_id": "SS_009", "type": "normal"}}, {"id": "SS_016", "name": "车公庄站", "category": "subway", "district": "西城", "longitude": 116.3567, "latitude": 39.9289, "details": {"category": "subway", "district": "西城", "latitude": 39.9289, "lines": ["2号线", "6号线"], "longitude": 116.3567, "name": "车公庄站", "station_id": "SS_016", "type": "transfer"}}, {"id": "SS_036", "name": "北京西站", "category": "subway", "district": "丰台", "longitude": 116.3289, "latitude": 39.8989, "details": {"category": "subway", "district": "丰台", "latitude": 39.8989, "lines": ["7号线", "9号线"], "longitude": 116.3289, "name": "北京西站", "station_id": "SS_036", "type": "transfer"}}, {"id": "F500_012", "name": "字节跳动", "category": "company", "district": "海淀", "longitude": 116.3289, "latitude": 39.9789, "details": {"address": "北京市海淀区北三环西路27号方恒时尚中心", "category": "company", "company_id": "F500_012", "district": "海淀", "industry": "互联网", "latitude": 39.9789, "longitude": 116.3289, "name": "字节跳动", "name_en": "ByteDance", "nearby_subway": "大钟寺站", "rank_2024": 167, "short_name": "字节"}}, {"id": "F500_014", "name": "小米集团", "category": "company", "district": "海淀", "longitude": 116.3256, "latitude": 40.0556, "details": {"address": "北京市海淀区西二旗中路33号小米科技园", "category": "company", "company_id": "F500_014", "district": "海淀", "industry": "科技", "latitude": 40.0556, "longitude": 116.3256, "name": "小米集团", "name_en": "Xiaomi", "nearby_subway": "西二旗站", "rank_2024": 266, "short_name": "小米"}}, {"id": "F500_019", "name": "中国铁建", "category": "company", "district": "海淀", "longitude": 116.2789, "latitude": 39.9089, "details": {"address": "北京市海淀区复兴路40号", "category": "company", "company_id": "F500_019", "district": "海淀", "industry": "建筑", "latitude": 39.9089, "longitude": 116.2789, "name": "中国铁建", "name_en": "China Railway Construction", "nearby_subway": "玉泉路站", "rank_2024": 111, "short_name": "铁建"}}, {"id": "LM_004", "name": "王府井步行街", "category": "landmark", "district": "东城", "longitude": 116.4212, "latitude": 39.9156, "details": {"address": "北京市东城区王府井大街", "category": "landmark", "district": "东城", "landmark_id": "LM_004", "latitude": 39.9156, "longitude": 116.4212, "name": "王府井步行街", "nearby_subway": "王府井站", "type": "shopping", "type_name": "商业街"}}, {"id": "SS_030", "name": "朝阳门站", "category": "subway", "district": "东城", "longitude": 116.4389, "latitude": 39.9312, "details": {"category": "subway", "district": "东城", "latitude": 39.9312, "lines": ["2号线", "6号线"], "longitude": 116.4389, "name": "朝阳门站", "station_id": "SS_030", "type": "transfer"}}, {"id": "SS_032", "name": "天安门东站", "category": "subway", "district": "东城", "longitude": 116.4089, "latitude": 39.9123, "details": {"category": "subway", "district": "东城", "latitude": 39.9123, "lines": ["1号线"], "longitude": 116.4089, "name": "天安门东站", "station_id": "SS_032", "type": "normal"}}, {"id": "SS_035", "name": "北京南站", "category": "subway", "district": "丰台", "longitude": 116.3812, "latitude": 39.8712, "details": {"category": "subway", "district": "丰台", "latitude": 39.8712, "lines": ["4号线大兴线", "14号线"], "longitude": 116.3812, "name": "北京南站", "station_id": "SS_035", "type": "transfer"}}, {"id": "SS_038", "name": "望京站", "category": "subway", "district": "朝阳", "longitude": 116.4812, "latitude": 40.0012, "details": {"category": "subway", "district": "朝阳", "latitude": 40.0012, "lines": ["14号线", "15号线"], "longitude": 116.4812, "name": "望京站", "station_id": "SS_038", "type": "transfer"}}, {"id": "SS_041", "name": "什刹海站", "category": "subway", "district": "西城", "longitude": 116.3912, "latitude": 39.9412, "details": {"category": "subway", "district": "西城", "latitude": 39.9412, "lines": ["8号线"], "longitude": 116.3912, "name": "什刹海站", "station_id": "SS_041", "type": "normal"}}, {"id": "SS_046", "name": "将台站", "category": "subway", "district": "朝阳", "longitude": 116.5012, "latitude": 39.9789, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9789, "lines": ["14号线"], "longitude": 116.5012, "name": "将台站", "station_id": "SS_046", "type": "normal"}}, {"id": "F500_006", "name": "中国建设银行", "category": "company", "district": "西城", "longitude": 116.3589, "latitude": 39.9189, "details": {"address": "北京市西城区金融大街25号", "category": "company", "company_id": "F500_006", "district": "西城", "industry": "银行", "latitude": 39.9189, "longitude": 116.3589, "name": "中国建设银行", "name_en": "China Construction Bank", "nearby_subway": "复兴门站", "rank_2024": 30, "short_name": "建行"}}, {"id": "F500_015", "name": "中国电信", "category": "company", "district": "西城", "longitude": 116.3612, "latitude": 39.9156, "details": {"address": "北京市西城区金融大街31号", "category": "company", "company_id": "F500_015", "district": "西城", "industry": "电信", "latitude": 39.9156, "longitude": 116.3612, "name": "中国电信", "name_en": "China Telecom", "nearby_subway": "复兴门站", "rank_2024": 132, "short_name": "电信"}}, {"id": "SS_002", "name": "上地站", "category": "subway", "district": "海淀", "longitude": 116.3389, "latitude": 40.0456, "details": {"category": "subway", "district": "海淀", "latitude": 40.0456, "lines": ["13号线"], "longitude": 116.3389, "name": "上地站", "station_id": "SS_002", "type": "normal"}}, {"id": "SS_015", "name": "昌平站", "category": "subway", "district": "昌平", "longitude": 116.2389, "latitude": 40.2183, "details": {"category": "subway", "district": "昌平", "latitude": 40.2183, "lines": ["昌平线"], "longitude": 116.2389, "name": "昌平站", "station_id": "SS_015", "type": "normal"}}, {"id": "SS_017", "name": "木樨地站", "category": "subway", "district": "西城", "longitude": 116.3481, "latitude": 39.9125, "details": {"category": "subway", "district": "西城", "latitude": 39.9125, "lines": ["1号线", "16号线"], "longitude": 116.3481, "name": "木樨地站", "station_id": "SS_017", "type": "transfer"}}, {"id": "SS_020", "name": "纪家庙站", "category": "subway", "district": "丰台", "longitude": 116.3678, "latitude": 39.8567, "details": {"category": "subway", "district": "丰台", "latitude": 39.8567, "lines": ["10号线"], "longitude": 116.3678, "name": "纪家庙站", "station_id": "SS_020", "type": "normal"}}, {"id": "SS_024", "name": "团结湖站", "category": "subway", "district": "朝阳", "longitude": 116.4567, "latitude": 39.9328, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9328, "lines": ["3号线", "10号线"], "longitude": 116.4567, "name": "团结湖站", "station_id": "SS_024", "type": "transfer"}}, {"id": "SS_040", "name": "北土城站", "category": "subway", "district": "朝阳", "longitude": 116.4012, "latitude": 39.9889, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9889, "lines": ["8号线", "10号线"], "longitude": 116.4012, "name": "北土城站", "station_id": "SS_040", "type": "transfer"}}, {"id": "F500_004", "name": "中国建筑集团", "category": "company", "district": "海淀", "longitude": 116.3389, "latitude": 39.9289, "details": {"address": "北京市海淀区三里河路15号", "category": "company", "company_id": "F500_004", "district": "海淀", "industry": "建筑", "latitude": 39.9289, "longitude": 116.3389, "name": "中国建筑集团", "name_en": "China State Construction Engineering", "nearby_subway": "木樨地站", "rank_2024": 9, "short_name": "中建"}}, {"id": "F500_018", "name": "中国中铁", "category": "company", "district": "丰台", "longitude": 116.3012, "latitude": 39.8389, "details": {"address": "北京市丰台区南四环西路128号", "category": "company", "company_id": "F500_018", "district": "丰台", "industry": "建筑", "latitude": 39.8389, "longitude": 116.3012, "name": "中国中铁", "name_en": "China Railway Engineering", "nearby_subway": "丰台科技园站", "rank_2024": 102, "short_name": "中铁"}}, {"id": "SS_008", "name": "双合站", "category": "subway", "district": "朝阳", "longitude": 116.5103, "latitude": 39.8667, "details": {"category": "subway", "district": "朝阳", "latitude": 39.8667, "lines": ["7号线"], "longitude": 116.5103, "name": "双合站", "station_id": "SS_008", "type": "normal"}}, {"id": "SS_037", "name": "三元桥站", "category": "subway", "district": "朝阳", "longitude": 116.4612, "latitude": 39.9612, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9612, "lines": ["10号线", "机场线"], "longitude": 116.4612, "name": "三元桥站", "station_id": "SS_037", "type": "transfer"}}, {"id": "F500_007", "name": "中国农业银行", "category": "company", "district": "东城", "longitude": 116.4389, "latitude": 39.9156, "details": {"address": "北京市东城区建国门内大街69号", "category": "company", "company_id": "F500_007", "district": "东城", "industry": "银行", "latitude": 39.9156, "longitude": 116.4389, "name": "中国农业银行", "name_en": "Agricultural Bank of China", "nearby_subway": "东单站", "rank_2024": 34, "short_name": "农行"}}, {"id": "LM_002", "name": "国贸商城", "category": "landmark", "district": "朝阳", "longitude": 116.4623, "latitude": 39.9106, "details": {"address": "北京市朝阳区建国门外大街1号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_002", "latitude": 39.9106, "longitude": 116.4623, "name": "国贸商城", "nearby_subway": "国贸站", "type": "shopping", "type_name": "购物中心"}}, {"id": "LM_011", "name": "朝阳公园", "category": "landmark", "district": "朝阳", "longitude": 116.4912, "latitude": 39.9512, "details": {"address": "北京市朝阳区朝阳公园南路1号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_011", "latitude": 39.9512, "longitude": 116.4912, "name": "朝阳公园", "nearby_subway": "朝阳公园站", "type": "park", "type_name": "公园"}}, {"id": "LM_018", "name": "国家游泳中心（水立方）", "category": "landmark", "district": "朝阳", "longitude": 116.3912, "latitude": 39.9989, "details": {"address": "北京市朝阳区天辰东路11号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_018", "latitude": 39.9989, "longitude": 116.3912, "name": "国家游泳中心（水立方）", "nearby_subway": "奥林匹克公园站", "type": "landmark", "type_name": "地标"}}, {"id": "LM_021", "name": "北京西站", "category": "landmark", "district": "丰台", "longitude": 116.3289, "latitude": 39.8989, "details": {"address": "北京市丰台区莲花池东路118号", "category": "landmark", "district": "丰台", "landmark_id": "LM_021", "latitude": 39.8989, "longitude": 116.3289, "name": "北京西站", "nearby_subway": "北京西站", "type": "transport", "type_name": "交通枢纽"}}, {"id": "SS_005", "name": "国贸站", "category": "subway", "district": "朝阳", "longitude": 116.4623, "latitude": 39.9106, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9106, "lines": ["1号线", "10号线"], "longitude": 116.4623, "name": "国贸站", "station_id": "SS_005", "type": "transfer"}}, {"id": "SS_012", "name": "阎村站", "category": "subway", "district": "房山", "longitude": 116.1123, "latitude": 39.7056, "details": {"category": "subway", "district": "房山", "latitude": 39.7056, "lines": ["燕房线"], "longitude": 116.1123, "name": "阎村站", "station_id": "SS_012", "type": "normal"}}, {"id": "SS_044", "name": "望京西站", "category": "subway", "district": "朝阳", "longitude": 116.4512, "latitude": 39.9912, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9912, "lines": ["13号线", "15号线"], "longitude": 116.4512, "name": "望京西站", "station_id": "SS_044", "type": "transfer"}}, {"id": "F500_016", "name": "中国联通", "category": "company", "district": "西城", "longitude": 116.3589, "latitude": 39.9145, "details": {"address": "北京市西城区金融大街21号", "category": "company", "company_id": "F500_016", "district": "西城", "industry": "电信", "latitude": 39.9145, "longitude": 116.3589, "name": "中国联通", "name_en": "China Unicom", "nearby_subway": "复兴门站", "rank_2024": 178, "short_name": "联通"}}, {"id": "F500_022", "name": "中国中化集团", "category": "company", "district": "西城", "longitude": 116.3634, "latitude": 39.9134, "details": {"address": "北京市西城区复兴门内大街28号", "category": "company", "company_id": "F500_022", "district": "西城", "industry": "化工", "latitude": 39.9134, "longitude": 116.3634, "name": "中国中化集团", "name_en": "Sinochem Holdings", "nearby_subway": "复兴门站", "rank_2024": 54, "short_name": "中化"}}, {"id": "LM_008", "name": "中关村广场", "category": "landmark", "district": "海淀", "longitude": 116.3189, "latitude": 39.9856, "details": {"address": "北京市海淀区中关村大街15号", "category": "landmark", "district": "海淀", "landmark_id": "LM_008", "latitude": 39.9856, "longitude": 116.3189, "name": "中关村广场", "nearby_subway": "中关村站", "type": "shopping", "type_name": "购物中心"}}, {"id": "LM_015", "name": "天安门广场", "category": "landmark", "district": "东城", "longitude": 116.4089, "latitude": 39.9123, "details": {"address": "北京市东城区东长安街", "category": "landmark", "district": "东城", "landmark_id": "LM_015", "latitude": 39.9123, "longitude": 116.4089, "name": "天安门广场", "nearby_subway": "天安门东站", "type": "landmark", "type_name": "地标"}}, {"id": "LM_019", "name": "首都国际机场T3航站楼", "category": "landmark", "district": "顺义", "longitude": 116.6212, "latitude": 40.0812, "details": {"address": "北京市顺义区首都机场路", "category": "landmark", "district": "顺义", "landmark_id": "LM_019", "latitude": 40.0812, "longitude": 116.6212, "name": "首都国际机场T3航站楼", "nearby_subway": "T3航站楼站", "type": "transport", "type_name": "交通枢纽"}}, {"id": "SS_047", "name": "东风北桥站", "category": "subway", "district": "朝阳", "longitude": 116.5112, "latitude": 39.9589, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9589, "lines": ["14号线"], "longitude": 116.5112, "name": "东风北桥站", "station_id": "SS_047", "type": "normal"}}, {"id": "SS_023", "name": "奥林匹克公园站", "category": "subway", "district": "朝阳", "longitude": 116.3892, "latitude": 39.9917, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9917, "lines": ["8号线", "15号线"], "longitude": 116.3892, "name": "奥林匹克公园站", "station_id": "SS_023", "type": "transfer"}}, {"id": "F500_025", "name": "五矿集团", "category": "company", "district": "海淀", "longitude": 116.3389, "latitude": 39.9289, "details": {"address": "北京市海淀区三里河路5号", "category": "company", "company_id": "F500_025", "district": "海淀", "industry": "金属", "latitude": 39.9289, "longitude": 116.3389, "name": "五矿集团", "name_en": "China Minmetals", "nearby_subway": "木樨地站", "rank_2024": 81, "short_name": "五矿"}}, {"id": "LM_006", "name": "颐堤港", "category": "landmark", "district": "朝阳", "longitude": 116.5012, "latitude": 39.9789, "details": {"address": "北京市朝阳区酒仙桥路18号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_006", "latitude": 39.9789, "longitude": 116.5012, "name": "颐堤港", "nearby_subway": "将台站", "type": "shopping", "type_name": "购物中心"}}, {"id": "SS_003", "name": "立水桥站", "category": "subway", "district": "昌平", "longitude": 116.4123, "latitude": 40.0289, "details": {"category": "subway", "district": "昌平", "latitude": 40.0289, "lines": ["5号线", "13号线"], "longitude": 116.4123, "name": "立水桥站", "station_id": "SS_003", "type": "transfer"}}, {"id": "SS_029", "name": "东直门站", "category": "subway", "district": "东城", "longitude": 116.4312, "latitude": 39.9456, "details": {"category": "subway", "district": "东城", "latitude": 39.9456, "lines": ["2号线", "13号线", "机场线"], "longitude": 116.4312, "name": "东直门站", "station_id": "SS_029", "type": "transfer"}}, {"id": "SS_045", "name": "望京南站", "category": "subway", "district": "朝阳", "longitude": 116.4912, "latitude": 39.9889, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9889, "lines": ["14号线"], "longitude": 116.4912, "name": "望京南站", "station_id": "SS_045", "type": "normal"}}, {"id": "F500_010", "name": "中国移动通信", "category": "company", "district": "西城", "longitude": 116.3589, "latitude": 39.9167, "details": {"address": "北京市西城区金融大街29号", "category": "company", "company_id": "F500_010", "district": "西城", "industry": "电信", "latitude": 39.9167, "longitude": 116.3589, "name": "中国移动通信", "name_en": "China Mobile Communications", "nearby_subway": "复兴门站", "rank_2024": 55, "short_name": "中国移动"}}, {"id": "LM_003", "name": "西单大悦城", "category": "landmark", "district": "西城", "longitude": 116.3812, "latitude": 39.9134, "details": {"address": "北京市西城区西单北大街131号", "category": "landmark", "district": "西城", "landmark_id": "LM_003", "latitude": 39.9134, "longitude": 116.3812, "name": "西单大悦城", "nearby_subway": "西单站", "type": "shopping", "type_name": "购物中心"}}, {"id": "LM_024", "name": "五道口购物中心", "category": "landmark", "district": "海淀", "longitude": 116.3389, "latitude": 39.9956, "details": {"address": "北京市海淀区成府路35号", "category": "landmark", "district": "海淀", "landmark_id": "LM_024", "latitude": 39.9956, "longitude": 116.3389, "name": "五道口购物中心", "nearby_subway": "五道口站", "type": "shopping", "type_name": "购物中心"}}, {"id": "SS_011", "name": "房山城关站", "category": "subway", "district": "房山", "longitude": 116.1458, "latitude": 39.7322, "details": {"category": "subway", "district": "房山", "latitude": 39.7322, "lines": ["燕房线"], "longitude": 116.1458, "name": "房山城关站", "station_id": "SS_011", "type": "normal"}}, {"id": "SS_028", "name": "五道口站", "category": "subway", "district": "海淀", "longitude": 116.3389, "latitude": 39.9956, "details": {"category": "subway", "district": "海淀", "latitude": 39.9956, "lines": ["13号线"], "longitude": 116.3389, "name": "五道口站", "station_id": "SS_028", "type": "normal"}}, {"id": "F500_020", "name": "中国交通建设集团", "category": "company", "district": "西城", "longitude": 116.3912, "latitude": 39.9589, "details": {"address": "北京市西城区德胜门外大街85号", "category": "company", "company_id": "F500_020", "district": "西城", "industry": "建筑", "latitude": 39.9589, "longitude": 116.3912, "name": "中国交通建设集团", "name_en": "China Communications Construction", "nearby_subway": "积水潭站", "rank_2024": 145, "short_name": "中交"}}, {"id": "LM_010", "name": "奥林匹克公园", "category": "landmark", "district": "朝阳", "longitude": 116.3892, "latitude": 39.9917, "details": {"address": "北京市朝阳区北辰东路15号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_010", "latitude": 39.9917, "longitude": 116.3892, "name": "奥林匹克公园", "nearby_subway": "奥林匹克公园站", "type": "park", "type_name": "公园"}}, {"id": "LM_012", "name": "天坛公园", "category": "landmark", "district": "东城", "longitude": 116.4112, "latitude": 39.8912, "details": {"address": "北京市东城区天坛东里甲1号", "category": "landmark", "district": "东城", "landmark_id": "LM_012", "latitude": 39.8912, "longitude": 116.4112, "name": "天坛公园", "nearby_subway": "天坛东门站", "type": "park", "type_name": "公园"}}, {"id": "LM_013", "name": "颐和园", "category": "landmark", "district": "海淀", "longitude": 116.2789, "latitude": 39.9989, "details": {"address": "北京市海淀区新建宫门路19号", "category": "landmark", "district": "海淀", "landmark_id": "LM_013", "latitude": 39.9989, "longitude": 116.2789, "name": "颐和园", "nearby_subway": "北宫门站", "type": "park", "type_name": "公园"}}, {"id": "LM_022", "name": "798艺术区", "category": "landmark", "district": "朝阳", "longitude": 116.5012, "latitude": 39.9889, "details": {"address": "北京市朝阳区酒仙桥路4号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_022", "latitude": 39.9889, "longitude": 116.5012, "name": "798艺术区", "nearby_subway": "望京南站", "type": "culture", "type_name": "文化"}}, {"id": "SS_010", "name": "土桥站", "category": "subway", "district": "通州", "longitude": 116.6789, "latitude": 39.8856, "details": {"category": "subway", "district": "通州", "latitude": 39.8856, "lines": ["八通线", "7号线"], "longitude": 116.6789, "name": "土桥站", "station_id": "SS_010", "type": "transfer"}}, {"id": "SS_050", "name": "九龙山站", "category": "subway", "district": "朝阳", "longitude": 116.4812, "latitude": 39.9012, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9012, "lines": ["7号线", "14号线"], "longitude": 116.4812, "name": "九龙山站", "station_id": "SS_050", "type": "transfer"}}, {"id": "F500_002", "name": "中国石化集团", "category": "company", "district": "朝阳", "longitude": 116.4389, "latitude": 39.9312, "details": {"address": "北京市朝阳区朝阳门北大街22号", "category": "company", "company_id": "F500_002", "district": "朝阳", "industry": "石油石化", "latitude": 39.9312, "longitude": 116.4389, "name": "中国石化集团", "name_en": "Sinopec Group", "nearby_subway": "朝阳门站", "rank_2024": 5, "short_name": "中石化"}}, {"id": "F500_008", "name": "中国银行", "category": "company", "district": "西城", "longitude": 116.3634, "latitude": 39.9134, "details": {"address": "北京市西城区复兴门内大街1号", "category": "company", "company_id": "F500_008", "district": "西城", "industry": "银行", "latitude": 39.9134, "longitude": 116.3634, "name": "中国银行", "name_en": "Bank of China", "nearby_subway": "复兴门站", "rank_2024": 37, "short_name": "中行"}}, {"id": "F500_013", "name": "百度公司", "category": "company", "district": "海淀", "longitude": 116.3189, "latitude": 40.0512, "details": {"address": "北京市海淀区上地十街10号百度大厦", "category": "company", "company_id": "F500_013", "district": "海淀", "industry": "互联网", "latitude": 40.0512, "longitude": 116.3189, "name": "百度公司", "name_en": "Baidu", "nearby_subway": "西二旗站", "rank_2024": 185, "short_name": "百度"}}, {"id": "F500_027", "name": "中信集团", "category": "company", "district": "朝阳", "longitude": 116.4612, "latitude": 39.9512, "details": {"address": "北京市朝阳区新源南路6号", "category": "company", "company_id": "F500_027", "district": "朝阳", "industry": "综合", "latitude": 39.9512, "longitude": 116.4612, "name": "中信集团", "name_en": "CITIC Group", "nearby_subway": "亮马桥站", "rank_2024": 71, "short_name": "中信"}}, {"id": "LM_009", "name": "华熙LIVE五棵松", "category": "landmark", "district": "海淀", "longitude": 116.2789, "latitude": 39.9089, "details": {"address": "北京市海淀区复兴路69号", "category": "landmark", "district": "海淀", "landmark_id": "LM_009", "latitude": 39.9089, "longitude": 116.2789, "name": "华熙LIVE五棵松", "nearby_subway": "五棵松站", "type": "shopping", "type_name": "购物中心"}}, {"id": "SS_007", "name": "百子湾站", "category": "subway", "district": "朝阳", "longitude": 116.5017, "latitude": 39.8917, "details": {"category": "subway", "district": "朝阳", "latitude": 39.8917, "lines": ["7号线"], "longitude": 116.5017, "name": "百子湾站", "station_id": "SS_007", "type": "normal"}}, {"id": "SS_014", "name": "学院桥站", "category": "subway", "district": "海淀", "longitude": 116.3456, "latitude": 39.9925, "details": {"category": "subway", "district": "海淀", "latitude": 39.9925, "lines": ["昌平线"], "longitude": 116.3456, "name": "学院桥站", "station_id": "SS_014", "type": "normal"}}, {"id": "F500_011", "name": "京东集团", "category": "company", "district": "大兴", "longitude": 116.5612, "latitude": 39.8089, "details": {"address": "北京市大兴区亦庄经济开发区科创十一街18号", "category": "company", "company_id": "F500_011", "district": "大兴", "industry": "电商", "latitude": 39.8089, "longitude": 116.5612, "name": "京东集团", "name_en": "JD.com", "nearby_subway": "经海路站", "rank_2024": 126, "short_name": "京东"}}, {"id": "F500_028", "name": "联想集团", "category": "company", "district": "海淀", "longitude": 116.3212, "latitude": 40.0489, "details": {"address": "北京市海淀区上地创业路6号", "category": "company", "company_id": "F500_028", "district": "海淀", "industry": "科技", "latitude": 40.0489, "longitude": 116.3212, "name": "联想集团", "name_en": "Lenovo Group", "nearby_subway": "西二旗站", "rank_2024": 248, "short_name": "联想"}}, {"id": "LM_025", "name": "望京SOHO", "category": "landmark", "district": "朝阳", "longitude": 116.4812, "latitude": 40.0012, "details": {"address": "北京市朝阳区望京街9号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_025", "latitude": 40.0012, "longitude": 116.4812, "name": "望京SOHO", "nearby_subway": "望京站", "type": "landmark", "type_name": "地标"}}, {"id": "SS_027", "name": "知春路站", "category": "subway", "district": "海淀", "longitude": 116.3289, "latitude": 39.9789, "details": {"category": "subway", "district": "海淀", "latitude": 39.9789, "lines": ["10号线", "13号线"], "longitude": 116.3289, "name": "知春路站", "station_id": "SS_027", "type": "transfer"}}, {"id": "SS_049", "name": "九龙山站", "category": "subway", "district": "朝阳", "longitude": 116.4812, "latitude": 39.9012, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9012, "lines": ["7号线", "14号线"], "longitude": 116.4812, "name": "九龙山站", "station_id": "SS_049", "type": "transfer"}}, {"id": "F500_009", "name": "中国人寿保险", "category": "company", "district": "西城", "longitude": 116.3612, "latitude": 39.9189, "details": {"address": "北京市西城区金融大街16号", "category": "company", "company_id": "F500_009", "district": "西城", "industry": "保险", "latitude": 39.9189, "longitude": 116.3612, "name": "中国人寿保险", "name_en": "China Life Insurance", "nearby_subway": "复兴门站", "rank_2024": 59, "short_name": "中国人寿"}}, {"id": "LM_016", "name": "故宫博物院", "category": "landmark", "district": "东城", "longitude": 116.4012, "latitude": 39.9189, "details": {"address": "北京市东城区景山前街4号", "category": "landmark", "district": "东城", "landmark_id": "LM_016", "latitude": 39.9189, "longitude": 116.4012, "name": "故宫博物院", "nearby_subway": "天安门东站", "type": "landmark", "type_name": "地标"}}, {"id": "SS_019", "name": "大红门站", "category": "subway", "district": "丰台", "longitude": 116.4328, "latitude": 39.8467, "details": {"category": "subway", "district": "丰台", "latitude": 39.8467, "lines": ["8号线", "10号线"], "longitude": 116.4328, "name": "大红门站", "station_id": "SS_019", "type": "transfer"}}, {"id": "SS_031", "name": "东单站", "category": "subway", "district": "东城", "longitude": 116.4212, "latitude": 39.9156, "details": {"category": "subway", "district": "东城", "latitude": 39.9156, "lines": ["1号线", "5号线"], "longitude": 116.4212, "name": "东单站", "station_id": "SS_031", "type": "transfer"}}, {"id": "F500_001", "name": "中国石油天然气集团", "category": "company", "district": "东城", "longitude": 116.4312, "latitude": 39.9456, "details": {"address": "北京市东城区东直门北大街9号", "category": "company", "company_id": "F500_001", "district": "东城", "industry": "石油石化", "latitude": 39.9456, "longitude": 116.4312, "name": "中国石油天然气集团", "name_en": "China National Petroleum", "nearby_subway": "东直门站", "rank_2024": 4, "short_name": "中石油"}}, {"id": "F500_017", "name": "中国邮政集团", "category": "company", "district": "西城", "longitude": 116.3612, "latitude": 39.9167, "details": {"address": "北京市西城区金融大街甲3号", "category": "company", "company_id": "F500_017", "district": "西城", "industry": "物流", "latitude": 39.9167, "longitude": 116.3612, "name": "中国邮政集团", "name_en": "China Post Group", "nearby_subway": "复兴门站", "rank_2024": 83, "short_name": "邮政"}}, {"id": "F500_021", "name": "中国海洋石油集团", "category": "company", "district": "东城", "longitude": 116.4412, "latitude": 39.9356, "details": {"address": "北京市东城区朝阳门北大街25号", "category": "company", "company_id": "F500_021", "district": "东城", "industry": "石油", "latitude": 39.9356, "longitude": 116.4412, "name": "中国海洋石油集团", "name_en": "China National Offshore Oil", "nearby_subway": "朝阳门站", "rank_2024": 56, "short_name": "中海油"}}, {"id": "LM_014", "name": "圆明园", "category": "landmark", "district": "海淀", "longitude": 116.3189, "latitude": 40.0012, "details": {"address": "北京市海淀区清华西路28号", "category": "landmark", "district": "海淀", "landmark_id": "LM_014", "latitude": 40.0012, "longitude": 116.3189, "name": "圆明园", "nearby_subway": "圆明园站", "type": "park", "type_name": "公园"}}, {"id": "LM_020", "name": "北京南站", "category": "landmark", "district": "丰台", "longitude": 116.3812, "latitude": 39.8712, "details": {"address": "北京市丰台区永外大街车站路12号", "category": "landmark", "district": "丰台", "landmark_id": "LM_020", "latitude": 39.8712, "longitude": 116.3812, "name": "北京南站", "nearby_subway": "北京南站", "type": "transport", "type_name": "交通枢纽"}}, {"id": "SS_013", "name": "黄村西大街站", "category": "subway", "district": "大兴", "longitude": 116.3456, "latitude": 39.7283, "details": {"category": "subway", "district": "大兴", "latitude": 39.7283, "lines": ["4号线大兴线"], "longitude": 116.3456, "name": "黄村西大街站", "station_id": "SS_013", "type": "normal"}}, {"id": "F500_003", "name": "国家电网", "category": "company", "district": "西城", "longitude": 116.3812, "latitude": 39.9123, "details": {"address": "北京市西城区西长安街86号", "category": "company", "company_id": "F500_003", "district": "西城", "industry": "电力", "latitude": 39.9123, "longitude": 116.3812, "name": "国家电网", "name_en": "State Grid", "nearby_subway": "西单站", "rank_2024": 3, "short_name": "国网"}}, {"id": "F500_023", "name": "中国宝武钢铁集团", "category": "company", "district": "东城", "longitude": 116.4412, "latitude": 39.9312, "details": {"address": "北京市东城区朝阳门北大街1号", "category": "company", "company_id": "F500_023", "district": "东城", "industry": "钢铁", "latitude": 39.9312, "longitude": 116.4412, "name": "中国宝武钢铁集团", "name_en": "China Baowu Steel Group", "nearby_subway": "朝阳门站", "rank_2024": 72, "short_name": "宝武"}}, {"id": "F500_029", "name": "中国华能集团", "category": "company", "district": "西城", "longitude": 116.3634, "latitude": 39.9123, "details": {"address": "北京市西城区复兴门内大街6号", "category": "company", "company_id": "F500_029", "district": "西城", "industry": "电力", "latitude": 39.9123, "longitude": 116.3634, "name": "中国华能集团", "name_en": "China Huaneng Group", "nearby_subway": "复兴门站", "rank_2024": 187, "short_name": "华能"}}, {"id": "LM_017", "name": "国家体育场（鸟巢）", "category": "landmark", "district": "朝阳", "longitude": 116.3912, "latitude": 39.9956, "details": {"address": "北京市朝阳区国家体育场南路1号", "category": "landmark", "district": "朝阳", "landmark_id": "LM_017", "latitude": 39.9956, "longitude": 116.3912, "name": "国家体育场（鸟巢）", "nearby_subway": "奥林匹克公园站", "type": "landmark", "type_name": "地标"}}, {"id": "SS_048", "name": "九龙山站", "category": "subway", "district": "朝阳", "longitude": 116.4812, "latitude": 39.9012, "details": {"category": "subway", "district": "朝阳", "latitude": 39.9012, "lines": ["7号线", "14号线"], "longitude": 116.4812, "name": "九龙山站", "station_id": "SS_048", "type": "transfer"}}, {"id": "SS_001", "name": "西二旗站", "category": "subway", "district": "海淀", "longitude": 116.3289, "latitude": 40.0567, "details": {"category": "subway", "district": "海淀", "latitude": 40.0567, "lines": ["13号线", "昌平线"], "longitude": 116.3289, "name": "西二旗站", "station_id": "SS_001", "type": "transfer"}}, {"id": "SS_018", "name": "陶然亭站", "category": "subway", "district": "西城", "longitude": 116.3812, "latitude": 39.8839, "details": {"category": "subway", "district": "西城", "latitude": 39.8839, "lines": ["4号线大兴线"], "longitude": 116.3812, "name": "陶然亭站", "station_id": "SS_018", "type": "normal"}}]}}}}
{"timestamp": "2026-02-28T16:33:51.171501", "scenario": "2_landmarks_list_filtered", "request": {"method": "GET", "path": "/api/landmarks", "params": {"category": "subway", "district": "海淀"}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"total": 7, "items": [{"id": "SS_028", "name": "五道口站", "category": "subway", "district": "海淀", "longitude": 116.3389, "latitude": 39.9956, "details": {"category": "subway", "district": "海淀", "latitude": 39.9956, "lines": ["13号线"], "longitude": 116.3389, "name": "五道口站", "station_id": "SS_028", "type": "normal"}}, {"id": "SS_014", "name": "学院桥站", "category": "subway", "district": "海淀", "longitude": 116.3456, "latitude": 39.9925, "details": {"category": "subway", "district": "海淀", "latitude": 39.9925, "lines": ["昌平线"], "longitude": 116.3456, "name": "学院桥站", "station_id": "SS_014", "type": "normal"}}, {"id": "SS_027", "name": "知春路站", "category": "subway", "district": "海淀", "longitude": 116.3289, "latitude": 39.9789, "details": {"category": "subway", "district": "海淀", "latitude": 39.9789, "lines": ["10号线", "13号线"], "longitude": 116.3289, "name": "知春路站", "station_id": "SS_027", "type": "transfer"}}, {"id": "SS_001", "name": "西二旗站", "category": "subway", "district": "海淀", "longitude": 116.3289, "latitude": 40.0567, "details": {"category": "subway", "district": "海淀", "latitude": 40.0567, "lines": ["13号线", "昌平线"], "longitude": 116.3289, "name": "西二旗站", "station_id": "SS_001", "type": "transfer"}}, {"id": "SS_026", "name": "中关村站", "category": "subway", "district": "海淀", "longitude": 116.3189, "latitude": 39.9856, "details": {"category": "subway", "district": "海淀", "latitude": 39.9856, "lines": ["4号线大兴线"], "longitude": 116.3189, "name": "中关村站", "station_id": "SS_026", "type": "normal"}}, {"id": "SS_039", "name": "六道口站", "category": "subway", "district": "海淀", "longitude": 116.3589, "latitude": 40.0012, "details": {"category": "subway", "district": "海淀", "latitude": 40.0012, "lines": ["15号线", "昌平线"], "longitude": 116.3589, "name": "六道口站", "station_id": "SS_039", "type": "transfer"}}, {"id": "SS_002", "name": "上地站", "category": "subway", "district": "海淀", "longitude": 116.3389, "latitude": 40.0456, "details": {"category": "subway", "district": "海淀", "latitude": 40.0456, "lines": ["13号线"], "longitude": 116.3389, "name": "上地站", "station_id": "SS_002", "type": "normal"}}]}}}}
{"timestamp": "2026-02-28T16:33:51.191517", "scenario": "3_landmarks_name_exact", "request": {"method": "GET", "path": "/api/landmarks/name/西二旗站"}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"id": "SS_001", "name": "西二旗站", "category": "subway", "district": "海淀", "longitude": 116.3289, "latitude": 40.0567, "details": {"category": "subway", "district": "海淀", "latitude": 40.0567, "lines": ["13号线", "昌平线"], "longitude": 116.3289, "name": "西二旗站", "station_id": "SS_001", "type": "transfer"}}}}}
{"timestamp": "2026-02-28T16:33:51.211513", "scenario": "4_landmarks_search", "request": {"method": "GET", "path": "/api/landmarks/search", "params": {"q": "西二旗"}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"total": 1, "items": [{"id": "SS_001", "name": "西二旗站", "category": "subway", "district": "海淀", "longitude": 116.3289, "latitude": 40.0567, "details": {"category": "subway", "district": "海淀", "latitude": 40.0567, "lines": ["13号线", "昌平线"], "longitude": 116.3289, "name": "西二旗站", "station_id": "SS_001", "type": "transfer"}}]}}}}
{"timestamp": "2026-02-28T16:33:51.232179", "scenario": "4b_landmarks_search_filtered", "request": {"method": "GET", "path": "/api/landmarks/search", "params": {"q": "百度", "category": "company", "district": "海淀"}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"total": 1, "items": [{"id": "F500_013", "name": "百度公司", "category": "company", "district": "海淀", "longitude": 116.3189, "latitude": 40.0512, "details": {"address": "北京市海淀区上地十街10号百度大厦", "category": "company", "company_id": "F500_013", "district": "海淀", "industry": "互联网", "latitude": 40.0512, "longitude": 116.3189, "name": "百度公司", "name_en": "Baidu", "nearby_subway": "西二旗站", "rank_2024": 185, "short_name": "百度"}}]}}}}
{"timestamp": "2026-02-28T16:33:51.251946", "scenario": "5_landmarks_by_id", "request": {"method": "GET", "path": "/api/landmarks/SS_001"}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"id": "SS_001", "name": "西二旗站", "category": "subway", "district": "海淀", "longitude": 116.3289, "latitude": 40.0567, "details": {"category": "subway", "district": "海淀", "latitude": 40.0567, "lines": ["13号线", "昌平线"], "longitude": 116.3289, "name": "西二旗站", "station_id": "SS_001", "type": "transfer"}}}}}
{"timestamp": "2026-02-28T16:33:51.271755", "scenario": "6_landmarks_stats", "request": {"method": "GET", "path": "/api/landmarks/stats"}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"by_category": {"company": 30, "landmark": 25, "subway": 50}, "by_district": {"东城": 14, "丰台": 7, "大兴": 2, "房山": 2, "昌平": 2, "朝阳": 33, "海淀": 19, "西城": 23, "通州": 1, "顺义": 2}, "total": 105}}}}
{"timestamp": "2026-02-28T16:33:51.291967", "scenario": "7_houses_init", "request": {"method": "POST", "path": "/api/houses/init", "headers": {"X-User-ID": "l00933108"}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"action": "reset_user", "message": "该用户状态覆盖已清空，房源恢复为初始状态", "user_id": "l00933108"}}}}
{"timestamp": "2026-02-28T16:33:51.314295", "scenario": "8_houses_stats", "request": {"method": "GET", "path": "/api/houses/stats", "headers": {"X-User-ID": "l00933108"}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"total": 2000, "by_status": {"available": 1804, "offline": 95, "rented": 101}, "by_district": {"东城": 246, "丰台": 136, "大兴": 25, "房山": 47, "昌平": 50, "朝阳": 660, "海淀": 318, "西城": 467, "通州": 27, "顺义": 24}, "by_bedrooms": {"1": 10, "2": 673, "3": 662, "4": 655}, "price_range": {"min": 550, "max": 28000, "avg": 8118}}}}}
{"timestamp": "2026-02-28T16:33:51.335731", "scenario": "9_houses_by_platform_default", "request": {"method": "GET", "path": "/api/houses/by_platform", "params": {}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"total\": 1804, \"page\": 1, \"page_size\": 10, \"items\": [{\"house_id\": \"HF_1\", \"community\": \"中国铁建原香汇\", \"district\": \"房山\", \"area\": \"房山城关\", \"address\": \"福宁街5号\", \"bedrooms\": 1, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 43, \"floor\": \"中层\", \"total_floors\": 16, \"orientation\": \"西北\", \"decoration\": \"精装\", \"price\": 2250, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"燕房线\", \"subway_distance\": 500, \"subway_station\": \"房山城关站\", \"commute_to_xierqi\": 79, \"available_from\": \"2026-03-01\", \"listing_platform\": \"安居客\", \"listing_url\": \"https://bj.zu.anjuke.com/\", \"tags\": [\"精装修\", \"近地铁\", \"近商超\", \"有电梯\", \"小户型\", \"水电费另付\", \"无中介\", \"押二付一\"], \"hidden_noise_level\": \"安静\", \"status\": \"available\", \"longitude\": 116.1458, \"latitude\": 39.7322, \"coordinate_system\": \"WGS84\"}, {\"house_id\": \"HF_2\", \"community\": \"保利锦上(二期)\", \"district\": \"朝阳\", \"area\": \"垡头\", \"address\": \"孛兴街9号\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 68, \"floor\": \"低层\", \"total_floors\": 21, \"orientation\": \"朝东\", \"decoration\": \"精装\", \"price\": 10350, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"7号线\", \"subway_distance\": 600, \"subway_station\": \"双合站\", \"commute_to_xierqi\": 48, \"available_from\": \"2026-02-20\", \"listing_platform\": \"安居客\", \"listing_url\": \"https://bj.zu.anjuke.com/\", \"tags\": [\"精装修\", \"近地铁\", \"采光好\", \"有电梯\", \"核心区\", \"水电费另付\", \"中介费一月租\", \"押一付一\"], \"hidden_noise_level\": \"中等\", \"status\": \"available\", \"longitude\": 116.5103, \"latitude\": 39.8667, \"coordinate_system\": \"WGS84\"}, {\"house_id\": \"HF_3\", \"community\": \"建清园(南区)\", \"district\": \"海淀\", \"area\": \"学院路\", \"address\": \"月泉路\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 85.7, \"floor\": \"低层\", \"total_floors\": 6, \"orientation\": \"朝东\", \"decoration\": \"简装\", \"price\": 7600, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": false, \"subway\": \"昌平线\", \"subway_dista..."}}
{"timestamp": "2026-02-28T16:33:51.356733", "scenario": "10_houses_by_platform_filtered", "request": {"method": "GET", "path": "/api/houses/by_platform", "params": {"district": "海淀", "min_price": 2000, "max_price": 6000, "bedrooms": "1,2", "rental_type": "整租", "max_subway_dist": 1000, "listing_platform": "安居客", "page": 1, "page_size": 5, "sort_by": "price", "sort_order": "asc"}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"total\": 1, \"page\": 1, \"page_size\": 5, \"items\": [{\"house_id\": \"HF_33\", \"community\": \"车道沟南里小区\", \"district\": \"海淀\", \"area\": \"紫竹桥\", \"address\": \"车道沟南路\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 48, \"floor\": \"高层\", \"total_floors\": 21, \"orientation\": \"朝西\", \"decoration\": \"简装\", \"price\": 5500, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"6/10号线\", \"subway_distance\": 300, \"subway_station\": \"车道沟站\", \"commute_to_xierqi\": 0, \"available_from\": \"2026-02-28\", \"listing_platform\": \"安居客\", \"listing_url\": \"https://bj.zu.anjuke.com/\", \"tags\": [\"近地铁\", \"采光好\", \"有电梯\", \"小户型\", \"核心区\", \"学区房\", \"水电费另付\", \"收中介费\", \"押二付一\"], \"hidden_noise_level\": \"中等\", \"status\": \"available\", \"longitude\": 116.3123, \"latitude\": 39.9567, \"coordinate_system\": \"WGS84\"}]}}"}}
{"timestamp": "2026-02-28T16:33:51.379229", "scenario": "11_houses_by_platform_链家", "request": {"method": "GET", "path": "/api/houses/by_platform", "params": {"listing_platform": "链家", "page": 1, "page_size": 3}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"total\": 1804, \"page\": 1, \"page_size\": 3, \"items\": [{\"house_id\": \"HF_1\", \"community\": \"中国铁建原香汇\", \"district\": \"房山\", \"area\": \"房山城关\", \"address\": \"福宁街5号\", \"bedrooms\": 1, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 43, \"floor\": \"中层\", \"total_floors\": 16, \"orientation\": \"西北\", \"decoration\": \"精装\", \"price\": 2070, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"燕房线\", \"subway_distance\": 500, \"subway_station\": \"房山城关站\", \"commute_to_xierqi\": 79, \"available_from\": \"2026-03-01\", \"listing_platform\": \"链家\", \"listing_url\": \"https://bj.lianjia.com/zufang/BJ1000001.html\", \"tags\": [\"精装修\", \"近地铁\", \"近商超\", \"有电梯\", \"小户型\", \"包水电费\", \"收中介费\", \"押二付一\"], \"hidden_noise_level\": \"安静\", \"status\": \"available\", \"longitude\": 116.1458, \"latitude\": 39.7322, \"coordinate_system\": \"WGS84\"}, {\"house_id\": \"HF_2\", \"community\": \"保利锦上(二期)\", \"district\": \"朝阳\", \"area\": \"垡头\", \"address\": \"孛兴街9号\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 68, \"floor\": \"低层\", \"total_floors\": 21, \"orientation\": \"朝东\", \"decoration\": \"精装\", \"price\": 9626, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"7号线\", \"subway_distance\": 600, \"subway_station\": \"双合站\", \"commute_to_xierqi\": 48, \"available_from\": \"2026-02-20\", \"listing_platform\": \"链家\", \"listing_url\": \"https://bj.lianjia.com/zufang/BJ1000002.html\", \"tags\": [\"精装修\", \"近地铁\", \"采光好\", \"有电梯\", \"核心区\", \"包水电费\", \"房东直租\", \"押一付一\"], \"hidden_noise_level\": \"中等\", \"status\": \"available\", \"longitude\": 116.5103, \"latitude\": 39.8667, \"coordinate_system\": \"WGS84\"}, {\"house_id\": \"HF_3\", \"community\": \"建清园(南区)\", \"district\": \"海淀\", \"area\": \"学院路\", \"address\": \"月泉路\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 85.7, \"floor\": \"低层\", \"total_floors\": 6, \"orientation\": \"朝东\", \"decoration\": \"简装\", \"price\": 7144, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": false,..."}}
{"timestamp": "2026-02-28T16:33:51.400805", "scenario": "11_houses_by_platform_58同城", "request": {"method": "GET", "path": "/api/houses/by_platform", "params": {"listing_platform": "58同城", "page": 1, "page_size": 3}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"total\": 1804, \"page\": 1, \"page_size\": 3, \"items\": [{\"house_id\": \"HF_1\", \"community\": \"中国铁建原香汇\", \"district\": \"房山\", \"area\": \"房山城关\", \"address\": \"福宁街5号\", \"bedrooms\": 1, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 43, \"floor\": \"中层\", \"total_floors\": 16, \"orientation\": \"西北\", \"decoration\": \"精装\", \"price\": 1755, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"燕房线\", \"subway_distance\": 500, \"subway_station\": \"房山城关站\", \"commute_to_xierqi\": 79, \"available_from\": \"2026-03-01\", \"listing_platform\": \"58同城\", \"listing_url\": \"https://bj.58.com/zufang/pn2000001.shtml\", \"tags\": [\"精装修\", \"近地铁\", \"近商超\", \"有电梯\", \"小户型\", \"免水电费\", \"无中介\", \"押一付一\"], \"hidden_noise_level\": \"安静\", \"status\": \"available\", \"longitude\": 116.1458, \"latitude\": 39.7322, \"coordinate_system\": \"WGS84\"}, {\"house_id\": \"HF_2\", \"community\": \"保利锦上(二期)\", \"district\": \"朝阳\", \"area\": \"垡头\", \"address\": \"孛兴街9号\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 68, \"floor\": \"低层\", \"total_floors\": 21, \"orientation\": \"朝东\", \"decoration\": \"精装\", \"price\": 8176, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"7号线\", \"subway_distance\": 600, \"subway_station\": \"双合站\", \"commute_to_xierqi\": 48, \"available_from\": \"2026-02-20\", \"listing_platform\": \"58同城\", \"listing_url\": \"https://bj.58.com/zufang/pn2000002.shtml\", \"tags\": [\"精装修\", \"近地铁\", \"采光好\", \"有电梯\", \"核心区\", \"免水电费\", \"收中介费\", \"可月付\"], \"hidden_noise_level\": \"中等\", \"status\": \"available\", \"longitude\": 116.5103, \"latitude\": 39.8667, \"coordinate_system\": \"WGS84\"}, {\"house_id\": \"HF_3\", \"community\": \"建清园(南区)\", \"district\": \"海淀\", \"area\": \"学院路\", \"address\": \"月泉路\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 85.7, \"floor\": \"低层\", \"total_floors\": 6, \"orientation\": \"朝东\", \"decoration\": \"简装\", \"price\": 6080, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": false, \"subw..."}}
{"timestamp": "2026-02-28T16:33:51.421613", "scenario": "11b_houses_by_platform_extended", "request": {"method": "GET", "path": "/api/houses/by_platform", "params": {"decoration": "精装", "orientation": "朝南", "elevator": "true", "min_area": 50, "max_area": 120, "commute_to_xierqi_max": 60, "page": 1, "page_size": 3}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"total\": 2, \"page\": 1, \"page_size\": 3, \"items\": [{\"house_id\": \"HF_17\", \"community\": \"润枫欣尚\", \"district\": \"昌平\", \"area\": \"立水桥\", \"address\": \"中东路5号\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 85, \"floor\": \"低层\", \"total_floors\": 32, \"orientation\": \"朝南\", \"decoration\": \"精装\", \"price\": 6000, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"5/13号线\", \"subway_distance\": 300, \"subway_station\": \"立水桥站\", \"commute_to_xierqi\": 0, \"available_from\": \"2026-03-01\", \"listing_platform\": \"安居客\", \"listing_url\": \"https://bj.zu.anjuke.com/\", \"tags\": [\"精装修\", \"近地铁\", \"朝南\", \"采光好\", \"有电梯\", \"水电费另付\", \"无中介\", \"可月付\"], \"hidden_noise_level\": \"吵闹\", \"status\": \"available\", \"longitude\": 116.4123, \"latitude\": 40.0289, \"coordinate_system\": \"WGS84\"}, {\"house_id\": \"HF_40\", \"community\": \"智学苑\", \"district\": \"海淀\", \"area\": \"西二旗\", \"address\": \"西二旗大街\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 74, \"floor\": \"高层\", \"total_floors\": 15, \"orientation\": \"朝南\", \"decoration\": \"精装\", \"price\": 12150, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"13号线/昌平线\", \"subway_distance\": 880, \"subway_station\": \"西二旗站\", \"commute_to_xierqi\": 14, \"available_from\": \"2026-03-05\", \"listing_platform\": \"安居客\", \"listing_url\": \"https://bj.zu.anjuke.com/\", \"tags\": [\"精装修\", \"朝南\", \"采光好\", \"有电梯\", \"核心区\", \"学区房\", \"免物业费\", \"收中介费\", \"可短租\"], \"hidden_noise_level\": \"安静\", \"status\": \"available\", \"longitude\": 116.3289, \"latitude\": 40.0567, \"coordinate_system\": \"WGS84\"}]}}"}}
{"timestamp": "2026-02-28T16:33:51.442883", "scenario": "12_houses_by_community", "request": {"method": "GET", "path": "/api/houses/by_community", "params": {"community": "中国铁建原香汇", "page": 1, "page_size": 5}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"total\": 1, \"page\": 1, \"page_size\": 1, \"items\": [{\"house_id\": \"HF_1\", \"community\": \"中国铁建原香汇\", \"district\": \"房山\", \"area\": \"房山城关\", \"address\": \"福宁街5号\", \"bedrooms\": 1, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 43, \"floor\": \"中层\", \"total_floors\": 16, \"orientation\": \"西北\", \"decoration\": \"精装\", \"price\": 2250, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"燕房线\", \"subway_distance\": 500, \"subway_station\": \"房山城关站\", \"commute_to_xierqi\": 79, \"available_from\": \"2026-03-01\", \"listing_platform\": \"安居客\", \"listing_url\": \"https://bj.zu.anjuke.com/\", \"tags\": [\"精装修\", \"近地铁\", \"近商超\", \"有电梯\", \"小户型\", \"水电费另付\", \"无中介\", \"押二付一\"], \"hidden_noise_level\": \"安静\", \"status\": \"available\", \"longitude\": 116.1458, \"latitude\": 39.7322, \"coordinate_system\": \"WGS84\"}]}}"}}
{"timestamp": "2026-02-28T16:33:51.463928", "scenario": "12b_houses_by_community_lianjia", "request": {"method": "GET", "path": "/api/houses/by_community", "params": {"community": "中国铁建原香汇", "listing_platform": "链家", "page": 1, "page_size": 5}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"total\": 1, \"page\": 1, \"page_size\": 1, \"items\": [{\"house_id\": \"HF_1\", \"community\": \"中国铁建原香汇\", \"district\": \"房山\", \"area\": \"房山城关\", \"address\": \"福宁街5号\", \"bedrooms\": 1, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 43, \"floor\": \"中层\", \"total_floors\": 16, \"orientation\": \"西北\", \"decoration\": \"精装\", \"price\": 2070, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"燕房线\", \"subway_distance\": 500, \"subway_station\": \"房山城关站\", \"commute_to_xierqi\": 79, \"available_from\": \"2026-03-01\", \"listing_platform\": \"链家\", \"listing_url\": \"https://bj.lianjia.com/zufang/BJ1000001.html\", \"tags\": [\"精装修\", \"近地铁\", \"近商超\", \"有电梯\", \"小户型\", \"包水电费\", \"收中介费\", \"押二付一\"], \"hidden_noise_level\": \"安静\", \"status\": \"available\", \"longitude\": 116.1458, \"latitude\": 39.7322, \"coordinate_system\": \"WGS84\"}]}}"}}
{"timestamp": "2026-02-28T16:33:51.485825", "scenario": "13_houses_nearby", "request": {"method": "GET", "path": "/api/houses/nearby", "params": {"landmark_id": "SS_001", "max_distance": 2000, "page": 1, "page_size": 5}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"landmark\": {\"id\": \"SS_001\", \"name\": \"西二旗站\", \"longitude\": 116.3289, \"latitude\": 40.0567}, \"total\": 102, \"items\": [{\"house_id\": \"HF_36\", \"community\": \"智学苑\", \"district\": \"海淀\", \"area\": \"西二旗\", \"address\": \"西二旗大街\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 78, \"floor\": \"中层\", \"total_floors\": 15, \"orientation\": \"南北\", \"decoration\": \"精装\", \"price\": 12550, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"13号线/昌平线\", \"subway_distance\": 800, \"subway_station\": \"西二旗站\", \"commute_to_xierqi\": 10, \"available_from\": \"2026-02-20\", \"listing_platform\": \"安居客\", \"listing_url\": \"https://bj.zu.anjuke.com/\", \"tags\": [\"精装修\", \"近地铁\", \"南北通透\", \"有电梯\", \"核心区\", \"学区房\", \"免物业费\", \"中介费一月租\", \"可月付\"], \"hidden_noise_level\": \"中等\", \"status\": \"available\", \"longitude\": 116.3289, \"latitude\": 40.0567, \"coordinate_system\": \"WGS84\", \"distance_to_landmark\": 0, \"walking_distance\": 0, \"walking_duration\": 0}, {\"house_id\": \"HF_37\", \"community\": \"智学苑\", \"district\": \"海淀\", \"area\": \"西二旗\", \"address\": \"西二旗大街\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 75, \"floor\": \"低层\", \"total_floors\": 15, \"orientation\": \"朝南\", \"decoration\": \"简装\", \"price\": 8200, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"13号线/昌平线\", \"subway_distance\": 850, \"subway_station\": \"西二旗站\", \"commute_to_xierqi\": 12, \"available_from\": \"2026-02-25\", \"listing_platform\": \"安居客\", \"listing_url\": \"https://bj.zu.anjuke.com/\", \"tags\": [\"朝南\", \"采光好\", \"有电梯\", \"核心区\", \"学区房\", \"免物业费\", \"中介费半月租\", \"押二付一\"], \"hidden_noise_level\": \"安静\", \"status\": \"available\", \"longitude\": 116.3289, \"latitude\": 40.0567, \"coordinate_system\": \"WGS84\", \"distance_to_landmark\": 0, \"walking_distance\": 0, \"walking_duration\": 0}, {\"house_id\": \"HF_38\", \"community\": \"智学苑\", \"district\": \"海淀\", \"area\": \"西二旗\", \"address\": \"西二旗大街\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 72, \"floor\": \"高层\", \"..."}}
{"timestamp": "2026-02-28T16:33:51.508058", "scenario": "13b_houses_nearby_by_name", "request": {"method": "GET", "path": "/api/houses/nearby", "params": {"landmark_id": "西二旗站", "max_distance": 2000, "listing_platform": "链家", "page": 1, "page_size": 3}}, "response": {"status_code": 200, "body": "{\"code\": 0, \"message\": \"success\", \"data\": {\"landmark\": {\"id\": \"SS_001\", \"name\": \"西二旗站\", \"longitude\": 116.3289, \"latitude\": 40.0567}, \"total\": 102, \"items\": [{\"house_id\": \"HF_36\", \"community\": \"智学苑\", \"district\": \"海淀\", \"area\": \"西二旗\", \"address\": \"西二旗大街\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 78, \"floor\": \"中层\", \"total_floors\": 15, \"orientation\": \"南北\", \"decoration\": \"精装\", \"price\": 11672, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"13号线/昌平线\", \"subway_distance\": 800, \"subway_station\": \"西二旗站\", \"commute_to_xierqi\": 10, \"available_from\": \"2026-02-20\", \"listing_platform\": \"链家\", \"listing_url\": \"https://bj.lianjia.com/zufang/BJ1000036.html\", \"tags\": [\"精装修\", \"近地铁\", \"南北通透\", \"有电梯\", \"核心区\", \"学区房\", \"免水电费\", \"收中介费\", \"押二付一\"], \"hidden_noise_level\": \"中等\", \"status\": \"available\", \"longitude\": 116.3289, \"latitude\": 40.0567, \"coordinate_system\": \"WGS84\", \"distance_to_landmark\": 0, \"walking_distance\": 0, \"walking_duration\": 0}, {\"house_id\": \"HF_37\", \"community\": \"智学苑\", \"district\": \"海淀\", \"area\": \"西二旗\", \"address\": \"西二旗大街\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, \"area_sqm\": 75, \"floor\": \"低层\", \"total_floors\": 15, \"orientation\": \"朝南\", \"decoration\": \"简装\", \"price\": 7708, \"price_unit\": \"元/月\", \"rental_type\": \"整租\", \"property_type\": \"住宅\", \"utilities_type\": \"民水民电\", \"elevator\": true, \"subway\": \"13号线/昌平线\", \"subway_distance\": 850, \"subway_station\": \"西二旗站\", \"commute_to_xierqi\": 12, \"available_from\": \"2026-02-25\", \"listing_platform\": \"链家\", \"listing_url\": \"https://bj.lianjia.com/zufang/BJ1000037.html\", \"tags\": [\"朝南\", \"采光好\", \"有电梯\", \"核心区\", \"学区房\", \"免水电费\", \"无中介\", \"押一付一\"], \"hidden_noise_level\": \"安静\", \"status\": \"available\", \"longitude\": 116.3289, \"latitude\": 40.0567, \"coordinate_system\": \"WGS84\", \"distance_to_landmark\": 0, \"walking_distance\": 0, \"walking_duration\": 0}, {\"house_id\": \"HF_38\", \"community\": \"智学苑\", \"district\": \"海淀\", \"area\": \"西二旗\", \"address\": \"西二旗大街\", \"bedrooms\": 2, \"livingrooms\": 1, \"bathrooms\": 1, ..."}}
{"timestamp": "2026-02-28T16:33:51.529278", "scenario": "14_houses_nearby_landmarks", "request": {"method": "GET", "path": "/api/houses/nearby_landmarks", "params": {"community": "中国铁建原香汇", "type": "shopping", "max_distance_m": 3000}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"community": "中国铁建原香汇", "type": "shopping", "total": 0, "items": null}}}}
{"timestamp": "2026-02-28T16:33:51.550670", "scenario": "14b_houses_nearby_landmarks_park", "request": {"method": "GET", "path": "/api/houses/nearby_landmarks", "params": {"community": "中国铁建原香汇", "type": "park", "max_distance_m": 3000}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"community": "中国铁建原香汇", "type": "park", "total": 0, "items": null}}}}
{"timestamp": "2026-02-28T16:33:51.570650", "scenario": "15_houses_detail", "request": {"method": "GET", "path": "/api/houses/HF_1"}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"house_id": "HF_1", "community": "中国铁建原香汇", "district": "房山", "area": "房山城关", "address": "福宁街5号", "bedrooms": 1, "livingrooms": 1, "bathrooms": 1, "area_sqm": 43, "floor": "中层", "total_floors": 16, "orientation": "西北", "decoration": "精装", "price": 2250, "price_unit": "元/月", "rental_type": "整租", "property_type": "住宅", "utilities_type": "民水民电", "elevator": true, "subway": "燕房线", "subway_distance": 500, "subway_station": "房山城关站", "commute_to_xierqi": 79, "available_from": "2026-03-01", "listing_platform": "安居客", "listing_url": "https://bj.zu.anjuke.com/", "tags": ["精装修", "近地铁", "近商超", "有电梯", "小户型", "水电费另付", "无中介", "押二付一"], "hidden_noise_level": "安静", "status": "available", "longitude": 116.1458, "latitude": 39.7322, "coordinate_system": "WGS84"}}}}
{"timestamp": "2026-02-28T16:33:51.590983", "scenario": "16_houses_listings", "request": {"method": "GET", "path": "/api/houses/listings/HF_1"}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"total": 3, "page": 1, "page_size": 3, "items": [{"house_id": "HF_1", "community": "中国铁建原香汇", "district": "房山", "area": "房山城关", "address": "福宁街5号", "bedrooms": 1, "livingrooms": 1, "bathrooms": 1, "area_sqm": 43, "floor": "中层", "total_floors": 16, "orientation": "西北", "decoration": "精装", "price": 1755, "price_unit": "元/月", "rental_type": "整租", "property_type": "住宅", "utilities_type": "民水民电", "elevator": true, "subway": "燕房线", "subway_distance": 500, "subway_station": "房山城关站", "commute_to_xierqi": 79, "available_from": "2026-03-01", "listing_platform": "58同城", "listing_url": "https://bj.58.com/zufang/pn2000001.shtml", "tags": ["精装修", "近地铁", "近商超", "有电梯", "小户型", "免水电费", "无中介", "押一付一"], "hidden_noise_level": "安静", "status": "available", "longitude": 116.1458, "latitude": 39.7322, "coordinate_system": "WGS84"}, {"house_id": "HF_1", "community": "中国铁建原香汇", "district": "房山", "area": "房山城关", "address": "福宁街5号", "bedrooms": 1, "livingrooms": 1, "bathrooms": 1, "area_sqm": 43, "floor": "中层", "total_floors": 16, "orientation": "西北", "decoration": "精装", "price": 2250, "price_unit": "元/月", "rental_type": "整租", "property_type": "住宅", "utilities_type": "民水民电", "elevator": true, "subway": "燕房线", "subway_distance": 500, "subway_station": "房山城关站", "commute_to_xierqi": 79, "available_from": "2026-03-01", "listing_platform": "安居客", "listing_url": "https://bj.zu.anjuke.com/", "tags": ["精装修", "近地铁", "近商超", "有电梯", "小户型", "水电费另付", "无中介", "押二付一"], "hidden_noise_level": "安静", "status": "available", "longitude": 116.1458, "latitude": 39.7322, "coordinate_system": "WGS84"}, {"house_id": "HF_1", "community": "中国铁建原香汇", "district": "房山", "area": "房山城关", "address": "福宁街5号", "bedrooms": 1, "livingrooms": 1, "bathrooms": 1, "area_sqm": 43, "floor": "中层", "total_floors": 16, "orientation": "西北", "decoration": "精装", "price": 2070, "price_unit": "元/月", "rental_type": "整租", "property_type": "住宅", "utilities_type": "民水民电", "elevator": true, "subway": "燕房线", "subway_distance": 500, "subway_station": "房山城关站", "commute_to_xierqi": 79, "available_from": "2026-03-01", "listing_platform": "链家", "listing_url": "https://bj.lianjia.com/zufang/BJ1000001.html", "tags": ["精装修", "近地铁", "近商超", "有电梯", "小户型", "包水电费", "收中介费", "押二付一"], "hidden_noise_level": "安静", "status": "available", "longitude": 116.1458, "latitude": 39.7322, "coordinate_system": "WGS84"}]}}}}
{"timestamp": "2026-02-28T16:33:51.610710", "scenario": "17_houses_rent", "request": {"method": "POST", "path": "/api/houses/HF_1/rent", "body": {"listing_platform": "安居客"}}, "response": {"status_code": 400, "body": {"code": 400, "message": "请提供 listing_platform 参数（链家、安居客、58同城）以明确租赁/操作的平台"}}}
{"timestamp": "2026-02-28T16:33:51.630510", "scenario": "18_houses_terminate", "request": {"method": "POST", "path": "/api/houses/HF_1/terminate", "body": {"listing_platform": "安居客"}}, "response": {"status_code": 400, "body": {"code": 400, "message": "请提供 listing_platform 参数（链家、安居客、58同城）以明确租赁/操作的平台"}}}
{"timestamp": "2026-02-28T16:33:51.650490", "scenario": "19_houses_offline", "request": {"method": "POST", "path": "/api/houses/HF_1/offline", "body": {"listing_platform": "安居客"}}, "response": {"status_code": 400, "body": {"code": 400, "message": "请提供 listing_platform 参数（链家、安居客、58同城）以明确租赁/操作的平台"}}}
{"timestamp": "2026-02-28T16:33:51.703696", "scenario": "20_houses_terminate_again", "request": {"method": "POST", "path": "/api/houses/HF_1/terminate", "body": {"listing_platform": "安居客"}}, "response": {"status_code": 200, "body": {"code": 0, "message": "success", "data": {"house_id": "HF_1", "community": "中国铁建原香汇", "district": "房山", "area": "房山城关", "address": "福宁街5号", "bedrooms": 1, "livingrooms": 1, "bathrooms": 1, "area_sqm": 43, "floor": "中层", "total_floors": 16, "orientation": "西北", "decoration": "精装", "price": 2250, "price_unit": "元/月", "rental_type": "整租", "property_type": "住宅", "utilities_type": "民水民电", "elevator": true, "subway": "燕房线", "subway_distance": 500, "subway_station": "房山城关站", "commute_to_xierqi": 79, "available_from": "2026-03-01", "listing_platform": "安居客", "listing_url": "https://bj.zu.anjuke.com/", "tags": ["精装修", "近地铁", "近商超", "有电梯", "小户型", "水电费另付", "无中介", "押二付一"], "hidden_noise_level": "安静", "status": "available", "longitude": 116.1458, "latitude": 39.7322, "coordinate_system": "WGS84"}}}}
{"timestamp": "2026-02-28T16:33:51.723766", "scenario": "21_houses_without_userid_400", "request": {"method": "GET", "path": "/api/houses/stats", "headers": "无 X-User-ID"}, "response": {"status_code": 400, "body": {"code": 400, "message": "请提供请求头 X-User-ID 以标识当前用户"}}}
```