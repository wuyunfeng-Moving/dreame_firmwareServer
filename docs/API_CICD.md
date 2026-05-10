# Dreame Firmware Server API 文档（CI/CD 集成版）

## 1. 文档目的

本文档基于当前工程中的服务实现整理，目标是指导本地 CI/CD 工具完成以下自动化动作：

- 固件制品推送：将构建产物上传到当前服务
- 固件制品拉取：查询可升级版本并下载对应固件
- 设备侧联调：校验设备当前版本是否可升级

当前工程是一个固件分发服务，不是 Git 仓库服务。
因此本文档中的“推送 / 拉取”指的是固件制品的上传、查询和下载，不是源码仓库级别的 Git push / git pull。

## 2. 服务概览

服务入口来自 [FirmwareServer.py](../FirmwareServer.py)：

- HTTP: `http://<host>:3000`
- HTTPS: `https://<host>:3443`

说明：

- 服务启动时会尝试同时启动 3000 和 3443 两个端口。
- HTTPS 依赖 `cert.pem` 和 `key.pem`，如果证书不存在，HTTPS 可能不可用。
- 对于下载 URL，当前代码中返回值固定拼接为 `http://<host>:3000/...`，即使查询请求来自 HTTPS。

## 3. 认证方式

### 3.1 Web 会话认证

当前工程没有提供独立的 Token API。
需要自动化上传固件时，应使用表单登录接口获取会话 Cookie，再带着 Cookie 调用受保护接口。

- 登录接口：`POST /login`
- Content-Type: `application/x-www-form-urlencoded`
- 成功后：返回 302，并在响应头中写入会话 Cookie

### 3.2 权限模型

- 管理员：可管理所有设备和固件
- 普通用户：只能看到被授权的设备型号，并且只能删除 / 编辑自己上传的固件
- 固件上传接口要求用户已登录
- 固件检查、版本列表、固件下载、设备状态上报等接口当前无需登录

### 3.3 默认管理员

服务启动时如果不存在管理员，会自动创建：

- 用户名：`admin`
- 密码：`admin123`

建议在实际环境中立即修改。

## 4. 推荐给 CI/CD 的接口清单

如果你的本地 CI/CD 目标是“构建后推送固件，再供设备或测试工具拉取”，建议只接入下列接口：

1. `POST /login`
2. `POST /firmwares/upload`
3. `POST /firmware/check`
4. `GET /firmware/versions/<model_number>`
5. `GET /firmware/download/<firmware_id>`
6. `GET /api/firmware/download/chunk/<firmware_id>`

其他路由多数是后台管理页面或人工运维入口，不适合作为 CI/CD 主流程接口。

## 5. 接口详解

### 5.1 登录

#### 请求

- Method: `POST`
- Path: `/login`
- Auth: 无
- Content-Type: `application/x-www-form-urlencoded`

表单字段：

- `username`: 用户名
- `password`: 密码

#### cURL 示例

```bash
curl -i -c cookies.txt \
  -X POST "http://127.0.0.1:3000/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=admin&password=admin123"
```

#### 成功行为

- HTTP 状态码通常为 `302`
- 响应包含会话 Cookie
- 重定向目标一般为 `/dashboard`

#### 失败行为

- 用户不存在或密码错误：重定向回登录页
- 用户未审批：重定向回登录页并提示未获批准

#### CI/CD 注意事项

- 这是 HTML 表单登录，不是 JSON 登录
- 自动化工具必须保存 Cookie，例如 `cookies.txt`
- 后续调用受保护接口时使用 `-b cookies.txt`

### 5.2 上传固件

这是当前工程中最接近“推送制品”的接口。

#### 请求

- Method: `POST`
- Path: `/firmwares/upload`
- Auth: 需要登录 Cookie
- Content-Type: `multipart/form-data`

表单字段：

- `device_id`: 设备型号 ID，不是设备型号字符串
- `version`: 固件版本
- `description`: 发布说明
- `compatible_versions`: 可多次提交，表示兼容版本列表
- `manual_compatible_version`: 手工输入的兼容版本，多个值使用分号 `;` 分隔
- `firmware_file`: 二进制固件文件

版本规则：

- 当目标设备类型是 `wifi` 时，`version` 必须是 `x.x.x`，例如 `1.0.0`
- 当目标设备类型是 `device` 时，`version` 必须是纯数字，例如 `100`

#### cURL 示例

```bash
curl -i -b cookies.txt \
  -X POST "http://127.0.0.1:3000/firmwares/upload" \
  -F "device_id=3c505d05-248e-408c-8069-74596a31b63f" \
  -F "version=100" \
  -F "description=CI build 2026-05-10" \
  -F "compatible_versions=90" \
  -F "compatible_versions=95" \
  -F "manual_compatible_version=96;97" \
  -F "firmware_file=@build/output/app.bin"
```

#### 成功行为

- HTTP 状态码通常为 `302`
- 成功后重定向到 `/firmwares?device_id=<device_id>`
- 服务端会自动：
  - 保存二进制文件到 `uploads/firmwares/`
  - 计算 CRC16
  - 在 `data/firmwares/` 下生成固件元数据 JSON
  - 默认将固件状态设置为 `active`

#### 失败行为

- 未登录：会跳转到登录页
- 设备不存在：返回上传页并提示错误
- 版本格式不合法：返回上传页并提示错误
- 设备下已存在相同版本同类型固件：返回上传页并提示错误
- 未上传文件：返回上传页并提示错误

#### CI/CD 注意事项

- 这是表单接口，不返回标准 JSON
- 你的 CI/CD 成功判断建议基于以下条件组合：
  - HTTP 状态码为 `302`
  - 响应头 `Location` 指向固件列表页
  - 上传后再调用版本查询接口确认版本已出现
- 上传前必须先拿到 `device_id`

### 5.3 检查设备是否有可升级固件

这是设备侧或自动化测试最核心的查询接口。

#### 请求

- Method: `POST`
- Path: `/firmware/check`
- Auth: 无
- Content-Type: `application/json`

请求体：

```json
{
  "device_model": "Z4000",
  "device_version": "100",
  "wifi_version": "1.0.0"
}
```

字段说明：

- `device_model`: 设备型号，例如 `Z4000`
- `device_version`: 当前设备固件版本，必须为纯数字字符串
- `wifi_version`: 当前 WiFi 固件版本，必须为 `x.x.x`

#### 成功响应示例

```json
{
  "status": "success",
  "message": "Firmware check completed",
  "device": {
    "current_version": "100",
    "latest_version": "101",
    "upgradable": true,
    "download_url": "http://127.0.0.1:3000/firmware/download/e306d3c7-e17f-497d-a217-a1a69e317b45",
    "crc16": 12345,
    "notes": "CI build 2026-05-10"
  },
  "wifi": {
    "current_version": "1.0.0",
    "latest_version": "1.0.1",
    "upgradable": true,
    "download_url": "http://127.0.0.1:3000/firmware/download/bd07b577-c661-4945-b05a-821f874a539b",
    "crc16": 23456,
    "notes": "WiFi hotfix"
  }
}
```

#### 常见失败响应

- `400`: 缺少必填字段
- `400`: `device_version` 不是纯数字
- `400`: `wifi_version` 不是 `x.x.x`
- `404`: 设备型号不存在
- `404`: 系统中不存在型号为 `wifi` 的 WiFi 设备模板

#### CI/CD 用途

- 回归测试阶段验证“新版本是否对指定旧版本开放升级”
- 设备模拟器拉取升级任务前先调用该接口
- 上传成功后做烟雾测试：验证指定兼容版本是否确实返回 `upgradable=true`

### 5.4 获取某型号的固件版本列表

#### 请求

- Method: `GET`
- Path: `/firmware/versions/<model_number>`
- Auth: 无
- Query: `firmware_type=device|wifi`

#### cURL 示例

```bash
curl "http://127.0.0.1:3000/firmware/versions/Z4000?firmware_type=device"
```

#### 成功响应示例

```json
{
  "model_number": "Z4000",
  "firmware_type": "device",
  "versions": [
    {
      "version": "101",
      "compatible_versions": ["100", "99"],
      "release_date": "2026-05-10T09:30:00",
      "size": 1048576,
      "crc": 12345,
      "description": "CI build 2026-05-10",
      "url": "http://127.0.0.1:3000/firmware/download/e306d3c7-e17f-497d-a217-a1a69e317b45"
    }
  ]
}
```

#### 失败响应

- `404`: 设备型号不存在

#### CI/CD 用途

- 上传后确认版本是否已入库
- 生成发布记录或测试报告
- 给下游工具提供下载 URL、CRC、兼容版本等元数据

### 5.5 下载完整固件

#### 请求

- Method: `GET`
- Path: `/firmware/download/<firmware_id>`
- Auth: 无

#### cURL 示例

```bash
curl -L \
  -o firmware.bin \
  "http://127.0.0.1:3000/firmware/download/e306d3c7-e17f-497d-a217-a1a69e317b45"
```

#### Range 断点续传示例

```bash
curl -L \
  -H "Range: bytes=0-1023" \
  -o part.bin \
  "http://127.0.0.1:3000/firmware/download/e306d3c7-e17f-497d-a217-a1a69e317b45"
```

#### 响应特征

- 全量下载成功：`200`
- Range 部分下载成功：`206`
- Range 非法或超出范围：`416`
- 响应头包含：
  - `Accept-Ranges: bytes`
  - `Content-Disposition: attachment; filename="..."`
  - `Content-Length`
  - Range 请求时还会返回 `Content-Range`

#### 失败响应

- `404`: 固件 ID 不存在
- `404`: 元数据存在但实际文件不存在

#### CI/CD 用途

- 拉取制品到测试机
- 断点续传下载大文件
- 配合 CRC 校验确认文件完整性

### 5.6 分块下载固件

这是一个 JSON 形式的下载接口，适合不方便直接处理二进制流的客户端。

#### 请求

- Method: `GET`
- Path: `/api/firmware/download/chunk/<firmware_id>`
- Auth: 无
- Query:
  - `chunk_size`: 每块字节数，默认 `1024`
  - `chunk_index`: 从 `0` 开始的块序号
  - `client_progress`: 客户端上报进度，可选

#### cURL 示例

```bash
curl "http://127.0.0.1:3000/api/firmware/download/chunk/e306d3c7-e17f-497d-a217-a1a69e317b45?chunk_size=4096&chunk_index=0"
```

#### 成功响应示例

```json
{
  "chunk_index": 0,
  "total_chunks": 256,
  "chunk_size": 4096,
  "data": "00112233aabbccdd",
  "progress": 0.39,
  "file_size": 1048576,
  "bytes_downloaded": 4096
}
```

#### 失败响应

- `400`: `chunk_size <= 0` 或 `chunk_index < 0`
- `400`: 请求的块超出范围
- `404`: 固件不存在
- `500`: 文件读取异常

#### CI/CD 用途

- 一些脚本环境不方便处理流式二进制下载时可备用
- 不建议作为首选下载方式，因为会额外产生十六进制编码开销

### 5.7 设备注册

#### 请求

- Method: `POST`
- Path: `/api/device/register`
- Auth: 无
- Content-Type: `application/json`

请求体示例：

```json
{
  "model_number": "Z4000",
  "serial_number": "SN0001",
  "firmware_version": "100"
}
```

#### 成功响应

```json
{
  "registered": true,
  "device_id": "Z4000_SN0001",
  "message": "Device registered successfully"
}
```

#### 注意

- 当前实现只是占位接口，没有持久化设备实例
- 更适合联调，不适合作为 CI/CD 核心依赖

### 5.8 设备状态上报

#### 请求

- Method: `POST`
- Path: `/api/device/status`
- Auth: 无
- Content-Type: `application/json`

请求体示例：

```json
{
  "model_number": "Z4000",
  "serial_number": "SN0001",
  "status": "online"
}
```

#### 成功响应

```json
{
  "updated": true,
  "message": "Device status updated successfully"
}
```

#### 注意

- 当前实现也是占位接口，没有真实落库逻辑

## 6. 面向本地 CI/CD 的推荐流程

### 6.1 推送流程

推荐步骤：

1. 调用 `POST /login` 获取登录 Cookie
2. 使用后台已有设备的 `device_id` 调用 `POST /firmwares/upload`
3. 调用 `GET /firmware/versions/<model_number>` 校验新版本已可见
4. 可选：调用 `POST /firmware/check` 验证兼容版本是否会返回可升级结果

### 6.2 拉取流程

推荐步骤：

1. 调用 `POST /firmware/check` 判断是否存在升级
2. 从响应中的 `download_url` 获取下载地址
3. 调用 `GET /firmware/download/<firmware_id>` 下载固件
4. 使用响应中的 `crc16` 或版本列表中的 `crc` 做校验

### 6.3 最小可执行脚本示例

```bash
set -euo pipefail

BASE_URL="http://127.0.0.1:3000"
COOKIE_FILE="cookies.txt"
DEVICE_ID="3c505d05-248e-408c-8069-74596a31b63f"
MODEL_NUMBER="Z4000"
VERSION="101"
BIN_FILE="build/output/app.bin"

curl -sS -i -c "$COOKIE_FILE" \
  -X POST "$BASE_URL/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=admin&password=admin123" >/tmp/login.out

curl -sS -i -b "$COOKIE_FILE" \
  -X POST "$BASE_URL/firmwares/upload" \
  -F "device_id=$DEVICE_ID" \
  -F "version=$VERSION" \
  -F "description=uploaded by local cicd" \
  -F "compatible_versions=100" \
  -F "firmware_file=@$BIN_FILE" >/tmp/upload.out

curl -sS "$BASE_URL/firmware/versions/$MODEL_NUMBER?firmware_type=device"
```

## 7. 返回码约定

当前工程没有统一错误码规范，主要遵循 HTTP 状态码和 JSON / HTML 页面组合：

- `200`: 成功
- `206`: Range 部分下载成功
- `302`: 登录或上传等表单接口成功后重定向
- `400`: 参数错误 / 请求体缺失 / 版本格式错误
- `403`: 已登录但没有访问权限
- `404`: 设备、固件或文件不存在
- `416`: Range 请求无效
- `500`: 服务端文件读取异常等未处理错误

## 8. 已知限制

### 8.1 上传接口不是 JSON API

当前上传接口是后台表单接口，自动化可以接，但不够稳定，也不利于标准 CI/CD 对接。

### 8.2 缺少设备列表公开 API

上传需要 `device_id`，但当前没有给未登录自动化工具提供一个标准 JSON 设备列表接口。
因此你的 CI/CD 工具目前需要：

- 预置 `device_id`
- 或额外登录后访问后台页面 / 受保护接口自行解析

### 8.3 固件校验接口实现有类型问题

路由定义为 `POST /firmware/verify/<int:firmware_id>`，但系统中的固件 ID 实际使用 UUID 字符串。
这意味着该接口按当前数据结构基本不可用，不建议你的 CI/CD 接入它。

### 8.4 WiFi 查询依赖固定型号

`POST /firmware/check` 会额外查找型号为 `wifi` 的设备作为 WiFi 固件模板。
如果系统中没有这个型号，接口会直接返回 `404`。

## 9. 对本地 CI/CD 的落地建议

如果你现在就要接入，建议按下面方式做：

1. 将“推送”定义为登录后调用 `/firmwares/upload` 上传构建产物。
2. 将“拉取”定义为调用 `/firmware/check` 或 `/firmware/versions/<model_number>` 获取下载地址，再调用 `/firmware/download/<firmware_id>` 下载。
3. 在 CI/CD 配置中固定维护设备的 `device_id` 与 `model_number` 映射表，避免运行时再去页面里解析。
4. 优先使用 HTTP 3000 进行自动化接入，除非你已准备好 HTTPS 证书。
5. 上传完成后增加一次版本查询或固件检查，作为发布成功的二次确认。

## 10. 后续优化建议

如果你希望这个工程更适合标准 CI/CD，下一步最值得补的接口是：

1. JSON 登录或 API Token 认证接口
2. 公开或受保护的设备列表 JSON 接口
3. 纯 JSON 的固件上传接口
4. 可直接返回结构化结果的上传成功响应
5. 修复 `/firmware/verify/<int:firmware_id>` 与 UUID ID 模型不一致的问题
