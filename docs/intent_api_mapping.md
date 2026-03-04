# 意图接口与仿真 API 映射说明

本文档说明意图层（Agent 工具参数、UserPreferences）与 [interface_simulate.md](./interface_simulate.md) 中仿真 API 的对应关系，供迭代三实现工具调用与过滤时使用。

---

## 一、update_preferences → 搜索相关 API

`update_preferences` 写入的 UserPreferences 用于 `search_by_preferences` 的搜索与后过滤。意图参数与仿真 API 的对应关系如下。

### 1.1 直接映射到 GET /api/houses/by_platform 的 query 参数

| 意图字段（UserPreferences） | 仿真 API query 参数 | 说明 |
|---------------------------|---------------------|------|
| location → 解析后的 districts | district | 行政区，逗号分隔 |
| location → 解析后的 areas | area | 商圈，逗号分隔 |
| min_price | min_price | 最低月租金（元） |
| max_price | max_price | 最高月租金（元） |
| bedrooms | bedrooms | 卧室数，逗号分隔如 1,2 |
| rental_type | rental_type | 整租 / 合租 |
| decoration | decoration | 精装/简装 等 |
| orientation | orientation | 朝南、南北 等 |
| elevator | elevator | 字符串 "true" / "false" |
| min_area | min_area | 最小面积（平米） |
| max_area | max_area | 最大面积（平米） |
| property_type | property_type | 住宅 / 公寓 |
| subway_line | subway_line | 如 13号线 |
| max_subway_dist | max_subway_dist | 最大地铁距离（米） |
| utilities_type | utilities_type | 民水民电 等 |
| available_before | available_from_before | 可入住日期上限，YYYY-MM-DD |
| max_commute_minutes | commute_to_xierqi_max | 到西二旗通勤上限（分钟） |
| sort_by | sort_by | price / area / subway |
| sort_order | sort_order | asc / desc |
| listing_platform | listing_platform | 链家 / 安居客 / 58同城 |

分页：实现时使用 page、page_size（如 page=1, page_size=200 拉取后做后过滤）。

### 1.2 location 与地标/商圈/小区

- **行政区/商圈**：通过 `resolve_location` 得到 district、area，仅走 `GET /api/houses/by_platform`，传 district、area。
- **地标/地铁站/小区名**：需先解析再选接口：
  - 地标名（如「国贸附近」）：先 `GET /api/landmarks/search?q=...` 或 `GET /api/landmarks/name/{name}` 得到 landmark_id，再 `GET /api/houses/nearby?landmark_id=...&max_distance=...`（参数与 interface_simulate 一致）。
  - 小区名：`GET /api/houses/by_community?community=...`。

### 1.3 仅在后端过滤/排序中使用的意图参数（不直接对应单一 API 参数）

以下字段**不**作为 by_platform / nearby / by_community 的 query 参数传入，而是在拿到 API 返回的列表后，在**后端过滤与排序（post_filter_and_rank）**中使用：

- **tag_requirements**：硬过滤，房源 `tags` 必须包含全部指定标签。
- **tag_preferences**：软加分，匹配则加分排序，不匹配不排除；含属性标签映射（有电梯、精装修、朝南、高层/低层、整租/合租等），见设计文档第八章。

### 1.4 payment_method / deposit_type / no_agent_fee

这三个独立字段在仿真 API 的 by_platform 中**无直接 query 参数**，通过**标签（tag）匹配**实现：

- `payment_method`（月付/季付/半年付/年付）→ 过滤/匹配房源 `tags` 中含对应付款标签的房源。
- `deposit_type`（押一/押二/押三）→ 过滤/匹配房源 `tags` 中含对应押金标签的房源。
- `no_agent_fee: true` → 过滤/匹配房源 `tags` 中含「房东直租」的房源（数据中无「无中介」标签，用「房东直租」）。

实现时在 post_filter_and_rank（或等价逻辑）中按设计文档 8.3 做 tag 硬过滤。

---

## 二、get_house_detail → 仿真 API

| 工具参数 | 仿真 API | 说明 |
|----------|----------|------|
| house_id | path 参数 | GET /api/houses/{house_id}，请求头带 X-User-ID |

无 query 参数，仅路径带 house_id。

---

## 三、get_house_listings → 仿真 API

| 工具参数 | 仿真 API | 说明 |
|----------|----------|------|
| house_id | path 参数 | GET /api/houses/listings/{house_id}，请求头带 X-User-ID |

无 query 参数。

---

## 四、execute_action → 仿真 API

| 工具参数 | 仿真 API | 说明 |
|----------|----------|------|
| action=rent | POST /api/houses/{house_id}/rent | query 必填 listing_platform（链家/安居客/58同城） |
| action=terminate | POST /api/houses/{house_id}/terminate | query 必填 listing_platform |
| action=offline | POST /api/houses/{house_id}/offline | query 必填 listing_platform |
| house_id | path | 房源 ID |
| listing_platform | query | 必填，枚举值同上 |

请求头：X-User-ID。body 无需传；listing_platform 以 query 形式传递（与 interface_simulate 一致）。

---

## 五、通用约定

- **请求头**：所有 `/api/houses/*` 请求必须带 `X-User-ID`（用户工号）；地标接口 `/api/landmarks/*` 不需要。
- **新 Session**：建议调用 `POST /api/houses/init` 做房源数据重置。
- **近距离**：近地铁建议 max_subway_dist=800（米），地铁可达 1000；地标附近 nearby 的 max_distance 默认 2000，与 interface_simulate 一致。
