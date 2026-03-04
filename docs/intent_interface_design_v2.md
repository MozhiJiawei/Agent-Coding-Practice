# 意图接口设计方案 v2

> 基于 final-test 全部 129 条用例及数据库统计分布重新设计，目标：覆盖所有场景、提升 LLM 提参正确率。

---

## 一、设计目标

1. **全场景覆盖**：涵盖闲聊、单/多条件搜索、商圈/地标搜索、地铁线路搜索、平台比价、标签类偏好（宠物/付款/看房/配套/退租等）、操作类（租房/退租/下架）。
2. **提参正确率最优**：参数命名贴近自然语言、枚举值约束明确、硬/软偏好边界清晰、描述简洁无歧义。
3. **标签偏好体系化**：将 85 种标签归类为语义参数，LLM 只需提取用户意图即可，代码侧完成标签匹配和过滤。

---

## 二、当前接口不足分析


| 问题                                  | 影响                                          |
| ----------------------------------- | ------------------------------------------- |
| 缺少标签类参数（宠物/付款/看房/配套/退租等）            | final-test 近 70% 用例涉及标签偏好，当前接口无法提取          |
| `decoration` 硬/软边界描述过长              | LLM 频繁混淆「精装修」属于硬约束还是软偏好                     |
| `soft_preferences` 内嵌 object 结构     | 嵌套 JSON 增加 LLM 生成错误率，且与直接字段职责重叠             |
| 缺少 `property_type`（住宅/公寓）           | 无法区分整租住宅 vs 合租公寓                            |
| `floor_pref` 仅在 soft_preferences 内  | 用户明确说「低层/高层」时无法硬过滤                          |
| 硬/软偏好分流机制过于复杂                       | LLM 需同时判断字段归属（硬约束 vs soft_preferences），出错率高 |
| `bedrooms` 描述不够明确                   | LLM 有时输出 `2` (int) 而非 `"2"` (string)        |
| `payment_method` 参数存在但未在 tool 定义中暴露 | 月付/季付等无法被 LLM 提取                            |


---

## 三、工具体系总览（5 工具）


| #   | 工具名                     | 职责           | 调用时机                             |
| --- | ----------------------- | ------------ | -------------------------------- |
| 1   | `update_preferences`    | 提取/更新用户租房偏好  | 用户表达任何新偏好时                       |
| 2   | `search_by_preferences` | 按已合并偏好搜索房源   | update_preferences 之后，或偏好已设仅需搜索时 |
| 3   | `get_house_detail`      | 获取单套房源完整详情   | 用户询问某套房的具体信息时                    |
| 4   | `get_house_listings`    | 获取房源跨平台挂牌记录  | 用户要求比较不同平台价格时                    |
| 5   | `execute_action`        | 执行租房/退租/下架操作 | 用户确认要租/退租/下架时                    |


### 调用链规则

```
用户有新偏好 + 找房意图 → update_preferences → search_by_preferences
用户仅找房（偏好已设）     → search_by_preferences
用户问某房详情             → get_house_detail
用户要比价                 → get_house_listings
用户要租/退/下架           → execute_action
闲聊/无找房意图            → 不调用工具，直接回复
```

---

## 四、各工具详细定义

### 4.1 `update_preferences`

**功能**：提取本轮用户新增/变更的租房偏好，合并到 session。不搜索房源。

**设计原则**：

- 每轮只提取 **本轮新增/变更** 的字段，未提及的字段不传
- 所有直接字段均为 **硬约束**（不满足则排除），不存在嵌套的软偏好对象
- 软偏好统一通过 `tag_preferences` 数组表达（匹配则加分，不匹配不排除）
- 消除 `soft_preferences` 嵌套结构，降低 LLM JSON 生成错误率

```json
{
  "type": "function",
  "function": {
    "name": "update_preferences",
    "description": "提取或更新用户的租房偏好，仅合并偏好不搜索。调用后必须再调用 search_by_preferences 获取匹配房源。每轮只提取本轮新增/变更的偏好。",
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
          "description": "噪音偏好。「安静/不要吵/隔音好/睡眠浅」→\"安静\""
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
          "description": "付款周期偏好。「月付/按月付」→月付，「季付」→季付"
        },
        "deposit_type": {
          "type": "string",
          "enum": ["押一", "押二", "押三"],
          "description": "押金偏好。「押一付一」→押一，「可以押二」→押二"
        },

        "tag_requirements": {
          "type": "array",
          "items": {"type": "string"},
          "description": "必须匹配的标签（硬约束，不匹配则排除）。从用户明确需求中提取，值必须从标签参考表中选择。示例：「要能养猫」→[\"可养猫\"]；「附近有公园」→[\"近公园\"]；「要24小时保安」→[\"24小时保安\"]；「有车库车位」→[\"车库车位\"]；「包水电费」→[\"包水电费\"]；「房东直租」→[\"房东直租\"]；「提前退租可协商」→[\"提前退租可协商\"]；多条件示例：「能养猫、附近有公园」→[\"可养猫\",\"近公园\"]"
        },
        "tag_preferences": {
          "type": "array",
          "items": {"type": "string"},
          "description": "偏好的标签（软约束，匹配则加分排序，不匹配不排除）。用户说「最好/希望/如果有就好/XX更好/尽量」时使用。可用值包括标签参考表中的所有标签，以及房源属性标签：有电梯、精装修、简装、豪华装修、朝南、南北通透、高层、低层、整租、合租。示例：「最好有电梯」→[\"有电梯\"]；「精装最好」→[\"精装修\"]；「最好朝南」→[\"朝南\"]；「有公园更好」→[\"近公园\"]；「最好高层」→[\"高层\"]；多条件示例：「最好精装、有电梯更好」→[\"精装修\",\"有电梯\"]"
        }
      },
      "required": []
    }
  }
}
```

#### 标签参考表（tag_requirements / tag_preferences 可用值）


| 类别                            | 可用标签值                                                                                                      |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **宠物**                        | `可养猫`、`可养狗`、`可养宠物`、`不可养宠物`、`仅限小型犬`、`可养宠物需宠物押金`                                                             |
| **付款周期**                      | `月付`、`季付`、`半年付`、`年付`                                                                                       |
| **押金**                        | `押一`、`押二`、`押三`                                                                                             |
| **中介/房源**                     | `房东直租`、`收中介费`                                                                                              |
| **合同/房东**                     | `合同规范条款清晰`、`合同不规范`、`房东好沟通`、`房东不配合`、`房东难联系`                                                                 |
| **看房方式**                      | `仅线下看房`、`仅线上VR看房`、`仅线上AR看房`、`仅线上图片看房`、`线下+线上`                                                              |
| **看房时间**                      | `全天可看房`、`仅周末看房`、`仅工作日看房`、`工作日9-18点`、`工作日14-18点`、`工作日9-12点`、`周末9-18点`、`周末14-18点`、`周末9-12点`                  |
| **租期**                        | `可月租`、`可租2个月`、`可租3个月`、`可租4个月`、`可租5个月`、`可半年租`、`可年租`、`仅接受年租`                                                 |
| **费用包含**                      | `包水电费`、`免水电费`、`水电费另付`、`免宽带费`、`包宽带`、`网费另付`、`包物业费`、`免物业费`、`物业费另付`、`包车位`、`免车位费`、`车位费另付`、`包取暖费`、`免取暖费`、`取暖费另付` |
| **退租/转租**                     | `提前退租可协商`、`提前退租扣押金`、`经同意可转租`、`不可转租`                                                                        |
| **小区管理**                      | `车库车位`、`露天车位`、`无车位`、`24小时保安`、`门禁刷卡`、`门禁形同虚设`、`无门禁`、`物业管理到位`、`物业管理差`、`绿化好环境佳`、`绿化少环境一般`                     |
| **周边配套**                      | `近公园`、`近学校`、`近菜市场`、`近银行`、`近医院`、`近餐饮`、`近健身房`、`近警察局`、`近商超`、`近加油站`                                            |
| **房屋特点**                      | `采光好`、`南北通透`、`高性价比`                                                                                        |
| **属性标签（仅用于 tag_preferences）** | `有电梯`、`精装修`、`简装`、`豪华装修`、`朝南`、`朝北`、`朝东`、`朝西`、`西北`、`高层`、`低层`、`整租`、`合租`                                       |


---

### 4.2 `search_by_preferences`

**功能**：按当前已合并的偏好搜索房源，返回 top 5 精简列表。

```json
{
  "type": "function",
  "function": {
    "name": "search_by_preferences",
    "description": "按当前偏好搜索房源，返回 top 5。必须在 update_preferences 之后调用。若本轮有新偏好须先 update_preferences，若偏好已在之前轮次设好可直接调用。",
    "parameters": {
      "type": "object",
      "properties": {},
      "required": []
    }
  }
}
```

---

### 4.3 `get_house_detail`

**功能**：获取单套房源完整详情。

```json
{
  "type": "function",
  "function": {
    "name": "get_house_detail",
    "description": "获取单套房源完整详情（地址、户型、面积、租金、装修、朝向、楼层、标签、噪音等级等）。用户问某套房的具体信息时调用。",
    "parameters": {
      "type": "object",
      "properties": {
        "house_id": {
          "type": "string",
          "description": "房源 ID，如 HF_38"
        }
      },
      "required": ["house_id"]
    }
  }
}
```

---

### 4.4 `get_house_listings`

**功能**：获取房源在链家/安居客/58同城的全部挂牌记录（比价）。

```json
{
  "type": "function",
  "function": {
    "name": "get_house_listings",
    "description": "获取指定房源在链家、安居客、58同城三个平台的挂牌记录，用于跨平台比价。用户问「各平台价格/哪个便宜」时调用。",
    "parameters": {
      "type": "object",
      "properties": {
        "house_id": {
          "type": "string",
          "description": "房源 ID，如 HF_4"
        }
      },
      "required": ["house_id"]
    }
  }
}
```

---

### 4.5 `execute_action`

**功能**：执行租房/退租/下架操作。

```json
{
  "type": "function",
  "function": {
    "name": "execute_action",
    "description": "对房源执行租房、退租或下架操作。用户确认「我要租/帮我租/办理租房」时调用 rent；「退租」时调用 terminate；「下架」时调用 offline。必须通过此工具完成操作，不能只回复文字。",
    "parameters": {
      "type": "object",
      "properties": {
        "action": {
          "type": "string",
          "enum": ["rent", "terminate", "offline"],
          "description": "rent=租房，terminate=退租，offline=下架"
        },
        "house_id": {
          "type": "string",
          "description": "房源 ID，如 HF_38"
        },
        "listing_platform": {
          "type": "string",
          "enum": ["链家", "安居客", "58同城"],
          "description": "平台，必填。未指定时默认安居客"
        }
      },
      "required": ["action", "house_id", "listing_platform"]
    }
  }
}
```

---

## 五、场景覆盖映射

### 5.1 核心搜索场景（API 硬约束）


| 用例场景    | 提取参数                    | 示例                                             |
| ------- | ----------------------- | ---------------------------------------------- |
| 按行政区    | `location`              | 「海淀区的房子」→ `location:["海淀"]`                    |
| 按商圈     | `location`              | 「望京商圈」→ `location:["望京"]`                      |
| 按地标     | `location`              | 「国贸附近」→ `location:["国贸附近"]`                    |
| 按地铁站    | `location`              | 「双合站附近」→ `location:["双合站"]`                    |
| 按小区名    | `location`              | 「建清园南区」→ `location:["建清园南区"]`                  |
| 按价格     | `min_price`/`max_price` | 「3000-6000」→ `min_price:3000, max_price:6000`  |
| 按预算     | `max_price`             | 「预算5000」→ `max_price:5000`                     |
| 按预算（约数） | `min_price`/`max_price` | 「3000左右」→ `min_price:2500, max_price:3500`     |
| 按户型     | `bedrooms`              | 「两居室」→ `bedrooms:"2"`                          |
| 多户型     | `bedrooms`              | 「两居或三居」→ `bedrooms:"2,3"`                      |
| 整租/合租   | `rental_type`           | 「整租/一个人住」→ `rental_type:"整租"`                  |
| 装修      | `decoration`            | 「精装修」→ `decoration:"精装"`                       |
| 电梯      | `elevator`              | 「要电梯/老人腿脚不便」→ `elevator:true`                  |
| 面积      | `min_area`/`max_area`   | 「60平以上」→ `min_area:60`                         |
| 近地铁     | `max_subway_dist`       | 「近地铁」→ `max_subway_dist:800`                   |
| 地铁距离    | `max_subway_dist`       | 「500米内」→ `max_subway_dist:500`                 |
| 地铁线路    | `subway_line`           | 「13号线沿线」→ `subway_line:"13号线"`（包含匹配，也命中换乘站如「13号线/昌平线」） |
| 水电类型    | `utilities_type`        | 「民水民电」→ `utilities_type:"民水民电"`                |
| 平台      | `listing_platform`      | 「58同城上的」→ `listing_platform:"58同城"`            |
| 入住日期    | `available_before`      | 「3月10号前」→ `available_before:"2026-03-10"`      |
| 通勤      | `max_commute_minutes`   | 「通勤30分钟」→ `max_commute_minutes:30`             |
| 安静      | `noise_preference`      | 「安静/不吵/隔音好」→ `noise_preference:"安静"`           |
| 朝向      | `orientation`           | 「朝南/南北通透」→ `orientation:"朝南"` 或 `"南北"`         |
| 楼层      | `floor_pref`            | 「高楼层/高层」→ `floor_pref:"高层"`                    |
| 排序      | `sort_by`/`sort_order`  | 「按价格从低到高」→ `sort_by:"price", sort_order:"asc"` |
| 物业类型    | `property_type`         | 「住宅」→ `property_type:"住宅"`                     |


### 5.2 标签类场景（tag_requirements / tag_preferences）


| 用例场景   | 提取为 tag_requirements                             | 用例编号示例                                                                                                                  |
| ------ | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| 养宠物    | `["可养猫"]` / `["可养狗"]` / `["可养宠物"]` / `["仅限小型犬"]` | c2,c27,c29,c31,c34,c54,c63,c65,c73,c84,c90,c113,c114,c121                                                               |
| 月付     | `["月付"]`                                         | c3,c6,c8,c19,c20,c25,c27,c35,c37,c38,c40,c41,c46,c47,c60,c61,c62,c75,c87,c97,c126,c129                                  |
| 押金     | `["押一"]` / `["押二"]`                              | c8,c34,c35,c40,c42,c62,c80,c85,c97,c123,c128,c129                                                                       |
| 房东直租   | `["房东直租"]`                                       | c3,c6,c25,c36,c41,c61,c86,c90,c108,c109                                                                                 |
| 无中介    | `["房东直租"]`（数据中无「无中介」标签，统一用「房东直租」） | c22,c25,c36,c41,c46,c61                                                                                                 |
| 看房方式   | `["仅线上VR看房"]` / `["仅线下看房"]` 等                    | c2,c9,c44,c51,c55,c66,c70,c106,c107,c117,c118                                                                           |
| 看房时间   | `["仅周末看房"]` / `["工作日14-18点"]` 等                  | c9,c13,c18,c27,c28,c40,c51,c54,c65,c85,c90,c106,c107,c114,c117,c118                                                     |
| 租期     | `["可月租"]` / `["可租3个月"]` / `["可半年租"]`             | c4,c38,c58,c68,c75,c94,c104,c115                                                                                        |
| 包水电费   | `["包水电费"]` / `["免水电费"]`                          | c5,c50,c66,c86,c120                                                                                                     |
| 包宽带    | `["免宽带费"]` / `["包宽带"]`                           | c5,c20,c28,c43,c49,c85,c122,c129                                                                                        |
| 包物业费   | `["包物业费"]` / `["免物业费"]`                          | c9,c13,c51,c71,c85                                                                                                      |
| 车位     | `["车库车位"]` / `["包车位"]` / `["免车位费"]`              | c9,c18,c28,c72,c85,c91,c94,c99,c102,c114,c119                                                                           |
| 提前退租   | `["提前退租可协商"]`                                    | c10,c44,c80                                                                                                             |
| 附近配套   | `["近公园"]` / `["近医院"]` / `["近学校"]` 等              | c2,c9,c12,c14,c16,c17,c18,c19,c26,c27,c29,c30,c31,c59,c64,c65,c71,c76,c81,c82,c84,c85,c93,c102,c105,c110,c114,c116,c129 |
| 24小时保安 | `["24小时保安"]`                                     | c27,c28,c83,c118,c129                                                                                                   |
| 门禁     | `["门禁刷卡"]`                                       | c83,c124                                                                                                                |
| 物业管理   | `["物业管理到位"]`                                     | c91,c113                                                                                                                |
| 绿化环境   | `["绿化好环境佳"]`                                     | c17,c26,c114                                                                                                            |
| 房东好沟通  | `["房东好沟通"]`                                      | c39,c40,c65,c92                                                                                                         |
| 采光好    | `["采光好"]`                                        | c35,c98                                                                                                                 |
| 南北通透   | `["南北通透"]`                                       | c44                                                                                                                     |
| 近餐饮    | `["近餐饮"]`                                        | c7,c18,c20,c27,c28,c30,c82                                                                                              |
| 近健身房   | `["近健身房"]`                                       | c17,c20,c28,c32,c110                                                                                                    |


### 5.3 独立字段场景


| 用例场景 | 提取参数                   | 用例编号示例                                 |
| ---- | ---------------------- | -------------------------------------- |
| 免中介费 | `no_agent_fee: true`   | c6,c22,c25,c36,c46                     |
| 付款方式 | `payment_method: "月付"` | c3,c19,c20,c25,c37,c38,c40,c41,c46,c47 |
| 押金类型 | `deposit_type: "押一"`   | c8,c35,c42,c62,c85,c97,c123,c128,c129  |


### 5.4 操作类场景


| 用例场景  | 调用工具                                 | 用例编号示例                                                       |
| ----- | ------------------------------------ | ------------------------------------------------------------ |
| 租房    | `execute_action(action="rent")`      | ev12,ev22,c44,c45,c60,c62,c76,c80,c81,c84,c86,c119,c120,c123 |
| 退租    | `execute_action(action="terminate")` | c80                                                          |
| 下架    | `execute_action(action="offline")`   | —                                                            |
| 跨平台比价 | `get_house_listings`                 | ev18,ev22,c45,c60,c84,c120,c123                              |
| 查看详情  | `get_house_detail`                   | ev06,ev07,ev12,ev13,ev19,ev30                                |


### 5.5 多轮对话场景


| 场景模式       | 处理方式                                                   | 用例编号示例                        |
| ---------- | ------------------------------------------------------ | ----------------------------- |
| 逐步补充偏好     | 每轮 update_preferences 增量合并                             | ev07,c2,c9,c13,c18,c20        |
| 调整预算       | update_preferences(max_price=新值)                       | ev13,c43,c49,c79,c94,c96,c101 |
| 换区看看       | update_preferences(location=[新区], clear_location=true) | ev06                          |
| 搜索→详情→租房   | search → get_detail → execute_action                   | ev12,ev22,c45,c60,c84         |
| 搜索→比价→租最便宜 | search → get_listings → execute_action                 | c45,c60,c84,c120,c123         |
| 闲聊→逐步引导    | 前几轮不调工具，有明确意图后再调用                                      | ev07,ev29,ev30                |


---

## 六、关键提参规则（写入 system prompt）

### 6.1 硬约束 vs 软偏好判断规则

**核心原则**：所有直接字段均为硬约束，软偏好统一走 `tag_preferences` 数组。

```
明确/肯定表达 → 硬约束字段 或 tag_requirements
  「要精装」→ decoration:"精装"
  「必须有电梯」→ elevator:true
  「只要整租」→ rental_type:"整租"
  「能养猫」→ tag_requirements:["可养猫"]
  「月付」→ payment_method:"月付"

模糊/期望表达 → tag_preferences（不设直接字段，避免硬过滤导致结果为零）
  「最好精装」→ tag_preferences:["精装修"]
  「有电梯更好」→ tag_preferences:["有电梯"]
  「如果有停车位就好了」→ tag_preferences:["车库车位"]
  「尽量整租」→ tag_preferences:["整租"]
  「最好朝南」→ tag_preferences:["朝南"]
  「高层更好」→ tag_preferences:["高层"]
```

**关键**：当用户说「最好XX」时，**不要** 设置对应的硬约束字段（如 `elevator`、`decoration`），而是将其放入 `tag_preferences`。这样可以避免因非核心条件导致搜索结果为零。

### 6.2 常见隐含意图提取


| 用户表达           | 提取参数                                              |
| -------------- | ------------------------------------------------- |
| 一个人住/自己住/不合租   | `rental_type: "整租"`                               |
| 合租/找室友/室友      | `rental_type: "合租"`                               |
| 单间             | `rental_type: "合租", bedrooms: "1"`                |
| 老人腿脚不便/不想爬楼    | `elevator: true`                                  |
| 近地铁/交通方便/地铁方便  | `max_subway_dist: 800`                            |
| 走路10分钟到地铁      | `max_subway_dist: 800`                            |
| 走路5分钟到地铁       | `max_subway_dist: 400`                            |
| 地铁可达           | `max_subway_dist: 1000`                           |
| 地铁1公里/两公里      | `max_subway_dist: 1000` / `2000`                  |
| 安静/不吵/隔音好/睡眠浅  | `noise_preference: "安静"`                          |
| 采光好/阳光/明亮      | `tag_requirements:["采光好"]` 或 `orientation: "朝南"`  |
| 南北通透/通风好       | `tag_requirements:["南北通透"]` 或 `orientation: "南北"` |
| 空房/自己带家具       | `decoration: "空房"`                                |
| XX左右（价格）       | `min_price: XX*0.8, max_price: XX*1.2`（上下浮动20%）   |
| 拎包入住           | `decoration: "精装"` 或 `decoration: "豪华"`           |
| 预算紧/手头紧        | 仅根据实际给出的数字设置 max_price                            |
| 3000左右         | `min_price: 2500, max_price: 3500`                |
| 3000以内/不超过3000 | `max_price: 3000`                                 |
| 短租/住几个月        | `tag_requirements` 中加对应租期标签                       |
| 可月租/短租         | `tag_requirements:["可月租"]`                        |
| 附近有公园/遛狗       | `tag_requirements:["近公园"]`                        |
| 附近有商场/超市       | `tag_requirements:["近商超"]`                        |
| 附近有餐馆/吃饭       | `tag_requirements:["近餐饮"]`                        |
| 附近有医院          | `tag_requirements:["近医院"]`                        |
| 附近有学校          | `tag_requirements:["近学校"]`                        |
| 附近有健身房         | `tag_requirements:["近健身房"]`                       |
| 婚房/新婚          | `decoration: "精装"` 或 `decoration: "豪华"`           |
| 三个人住各一间        | `bedrooms: "3", rental_type: "整租"`                |
| 每人N元/人均N元     | `max_price: N × 合租人数`（如「每人两千，两人合租」→ `max_price: 4000`） |


### 6.3 价格「左右」处理约定

当用户说「N元左右」时，建议浮动 ±20%（即 min_price = N×0.8，max_price = N×1.2），但上下限取整百：

- 「3000左右」→ `min_price: 2400, max_price: 3600`
- 「5000左右」→ `min_price: 4000, max_price: 6000`

### 6.4 soft_preferences 移除后的迁移规则

v1 中 `soft_preferences` 覆盖的场景，在 v2 中统一通过 `tag_preferences` 处理：


| 用户表达        | v1 做法                                     | v2 做法                      |
| ----------- | ----------------------------------------- | -------------------------- |
| 「有电梯更好」     | `soft_preferences: {"elevator": true}`    | `tag_preferences: ["有电梯"]` |
| 「最好精装」      | `soft_preferences: {"decoration": "精装"}`  | `tag_preferences: ["精装修"]` |
| 「精装最好，简装也行」 | `soft_preferences: {"decoration": "精装"}`  | `tag_preferences: ["精装修"]` |
| 「最好整租」      | `soft_preferences: {"rental_type": "整租"}` | `tag_preferences: ["整租"]`  |
| 「最好朝南」      | `soft_preferences: {"orientation": "朝南"}` | `tag_preferences: ["朝南"]`  |
| 「高层更好」      | `soft_preferences: {"floor_pref": "高层"}`  | `tag_preferences: ["高层"]`  |


**注意**：当用户同时表达硬约束和软偏好时，硬约束用直接字段，软偏好用 `tag_preferences`，两者互不冲突：

- 「要精装，最好有电梯」→ `decoration: "精装"` + `tag_preferences: ["有电梯"]`
- 「必须近地铁，最好朝南」→ `max_subway_dist: 800` + `tag_preferences: ["朝南"]`

### 6.5 tag_requirements vs tag_preferences 使用规则

```
用户语气     → 使用字段
─────────────────────────────
「要/必须/得/需要」  → tag_requirements（硬约束）
「最好/希望/如果有」 → tag_preferences（软偏好）
```

**示例**：

- 「要能养猫」→ `tag_requirements: ["可养猫"]`
- 「最好有公园」→ `tag_preferences: ["近公园"]`
- 「月付，近地铁」→ `tag_requirements: ["月付"]`, `max_subway_dist: 800`

### 6.6 payment_method / deposit_type / no_agent_fee 与 tag 的关系

这三个独立字段同时也会自动映射为 tag 进行匹配：

- `payment_method: "月付"` → 自动匹配 tags 含 `月付` 的房源
- `deposit_type: "押一"` → 自动匹配 tags 含 `押一` 的房源
- `no_agent_fee: true` → 自动匹配 tags 含 `房东直租` 的房源

因此 LLM 可以选择用独立字段 **或** tag_requirements，效果一致。推荐对于付款/押金/中介用独立字段（更语义化），对于其他标签用 tag_requirements/tag_preferences。

---

## 七、UserPreferences 数据模型变更

```python
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

    # ── 标签匹配 ──
    tag_requirements: list[str] = []     # 硬约束标签（不匹配则排除）
    tag_preferences: list[str] = []      # 软偏好标签（匹配加分，不排除）

    # ── 上下文记忆 ──
    mentioned_house_ids: list[str] = []
    current_focus_house_id: Optional[str] = None
```

---

## 八、post_filter_and_rank 变更要点

在现有硬过滤和加分逻辑基础上，增加标签匹配：

### 8.0 floor_pref 硬过滤（含 `共N层` 映射）

数据中 `floor` 字段除 `低层/中层/高层` 外，还有 `共N层` 格式（约 8.8% 房源）。硬过滤时需额外映射：

```python
if prefs.floor_pref:
    floor_val = item.get("floor", "")
    if prefs.floor_pref in floor_val:
        pass  # 直接匹配
    elif floor_val.startswith("共"):
        total = int(floor_val.replace("共", "").replace("层", ""))
        if prefs.floor_pref == "低层" and total <= 6:
            pass  # 总层数≤6的低层建筑视为低层
        else:
            continue  # 不匹配则排除
    else:
        continue
```

### 8.1 tag_requirements 硬过滤

```python
if prefs.tag_requirements:
    house_tags = set(item.get("tags", []))
    if not all(tag in house_tags for tag in prefs.tag_requirements):
        continue
```

### 8.2 tag_preferences 加分（含属性标签映射）

```python
if prefs.tag_preferences:
    house_tags = set(item.get("tags", []))
    for tag in prefs.tag_preferences:
        # 先检查 tags 数组中是否直接匹配
        if tag in house_tags:
            score += 5
            continue
        # 属性标签映射：检查房源的结构化字段
        if tag == "有电梯" and item.get("elevator"):
            score += 5
        elif tag == "精装修" and item.get("decoration") == "精装":
            score += 5
        elif tag == "简装" and item.get("decoration") == "简装":
            score += 5
        elif tag == "豪华装修" and item.get("decoration") == "豪华":
            score += 5
        elif tag in ("朝南", "朝北", "朝东", "朝西", "南北", "东西", "西北"):
            ori = tag.replace("朝", "")
            if ori in (item.get("orientation") or ""):
                score += 10
        elif tag in ("高层", "中层", "低层"):
            floor_val = item.get("floor") or ""
            # 直接匹配"高层/中层/低层"，或将"共N层"映射为低层（总层数≤6视为低层建筑）
            if tag in floor_val:
                score += 5
            elif floor_val.startswith("共") and tag == "低层":
                total = int(floor_val.replace("共", "").replace("层", ""))
                if total <= 6:
                    score += 5
        elif tag == "整租" and item.get("rental_type") == "整租":
            score += 8
        elif tag == "合租" and item.get("rental_type") == "合租":
            score += 8
```

### 8.3 payment_method / deposit_type / no_agent_fee 标签映射

```python
# 付款方式 → tag 硬过滤
if prefs.payment_method:
    house_tags = set(item.get("tags", []))
    if prefs.payment_method not in house_tags:
        continue

# 押金类型 → tag 硬过滤
if prefs.deposit_type:
    house_tags = set(item.get("tags", []))
    if prefs.deposit_type not in house_tags:
        continue

# 免中介 → tag 硬过滤（数据中仅存在「房东直租」标签，不存在「无中介」标签）
if prefs.no_agent_fee:
    house_tags = set(item.get("tags", []))
    if "房东直租" not in house_tags:
        continue
```

### 8.4 subway_line 包含匹配

数据中存在复合线路值（如 `13号线/昌平线`、`2/6/13/16号线/4号线大兴线`），`subway_line` 过滤使用包含匹配：

```python
if prefs.subway_line:
    house_subway = item.get("subway", "")
    if prefs.subway_line not in house_subway:
        continue
```

---

## 九、与旧接口的对比


| 维度                     | v1（当前）                   | v2（新设计）                            |
| ---------------------- | ------------------------ | ---------------------------------- |
| 工具数                    | 5                        | 5（不变）                              |
| update_preferences 参数数 | 20                       | 26（+6）                             |
| 标签偏好支持                 | 无                        | tag_requirements + tag_preferences |
| 付款/押金                  | 无                        | payment_method + deposit_type      |
| 免中介                    | 有 no_agent_fee 但未在工具定义暴露 | 暴露为正式参数                            |
| 楼层偏好                   | 仅在 soft_preferences 内    | 提升为独立硬约束参数 floor_pref              |
| 物业类型                   | 无                        | 新增 property_type                   |
| 装修描述                   | 冗长易混淆                    | 简化 + enum 约束                       |
| soft_preferences       | 嵌套 object（5 个子字段）        | **已移除**，统一由 tag_preferences 承载     |
| bedrooms               | 描述模糊                     | 明确格式 + 示例                          |
| 场景覆盖                   | ~60%（不含标签）               | ~100%（含全部标签场景）                     |


---

## 十、实现优先级


| 优先级 | 变更项                                        | 影响范围              |
| --- | ------------------------------------------ | ----------------- |
| P0  | TOOLS 定义更新（新增 6 个参数，移除 soft_preferences）   | tools.py TOOLS 列表 |
| P0  | UserPreferences 新增字段 + 移除 soft_preferences | tools.py 数据模型     |
| P0  | post_filter_and_rank 增加标签过滤 + 属性标签映射加分     | tools.py 过滤逻辑     |
| P0  | update_preferences 函数处理新参数 + 移除 soft 合并逻辑  | tools.py 合并逻辑     |
| P1  | system prompt 更新（提参规则、标签表、移除 soft 相关指导）    | main.py / prompt  |
| P2  | 测试用例对齐验证（ev32 等用例的 soft_preferences 断言需调整） | test_cases.yaml   |


