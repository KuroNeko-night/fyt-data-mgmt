/**
 * 会话令牌访问器。
 *
 * 登录会话实际由服务端写入 HttpOnly Cookie；这里保留空实现以兼容旧调用方和
 * 未来需要显式 `X-Session-Token` 请求头的场景。`api.ts` 中的 `request` 依赖
 * `getToken` 决定是否附加该请求头。
 */
export function getToken() { return ""; }
export function setToken(_token: string) {}
export function clearToken() {}
