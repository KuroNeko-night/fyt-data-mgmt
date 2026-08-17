/**
 * 团队文件数据库页面。
 *
 * 面向数据库功能的客户入口：上传文件副本、按可见范围与业务分类检索、
 * 下载/编辑元数据、替换内容，并把删除动作交给服务端回收站策略。
 */
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  deleteLibraryFile,
  downloadLibraryFile,
  listLibraryFiles,
  replaceLibraryFile,
  updateLibraryFile,
  uploadLibraryFile,
  type LibraryFile,
  type LibraryResponse,
  type LibraryScope,
} from "./api";
import { Icon } from "./icons";
import EmptyState from "./ui/EmptyState";

/** 列表显示范围：全部可见、团队共享、私有或仅自己。 */
type LibraryFilter = "all" | "team" | "private" | "mine";

/** 把文件字节数转换成数据库列表和配额卡片使用的紧凑标签。 */
function sizeLabel(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** 将服务端 UTC 时间转换成当前浏览器所在时区的完整中文时间。 */
function timeLabel(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

/** 将文件可见范围转换成客户界面文案。 */
function scopeLabel(scope: LibraryScope) {
  return scope === "team" ? "团队共享" : "仅自己";
}

/** 团队文件数据库页面：负责上传、分类检索、下载、元数据编辑、替换和回收站删除。 */
export function FileLibraryPage() {
  const [data, setData] = useState<LibraryResponse | null>(null);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<LibraryFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [queryInput, setQueryInput] = useState(""); // 输入草稿与已提交查询分离，输入时不连续请求服务端。
  const [query, setQuery] = useState("");
  const [refreshKey, setRefreshKey] = useState(0); // 自增即可强制重新加载当前筛选页，无需伪造其他参数。
  const [loading, setLoading] = useState(true);
  // busy 使用“操作:id”格式区分上传、下载、编辑、替换和删除，同时互斥写操作。
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadScope, setUploadScope] = useState<LibraryScope>("team");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [editFile, setEditFile] = useState<LibraryFile | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editScope, setEditScope] = useState<LibraryScope>("team");
  const [editCategory, setEditCategory] = useState("");
  const [replaceTarget, setReplaceTarget] = useState<LibraryFile | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const replaceInputRef = useRef<HTMLInputElement | null>(null);

  /** 按当前分页、搜索、范围和业务分类从服务端读取可见文件。 */
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await listLibraryFiles({ page, page_size: 20, q: query, scope: filter, category: categoryFilter }));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "数据库文件读取失败");
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, filter, page, query, refreshKey]);

  useEffect(() => { void load(); }, [load]);

  /** 合并拖放与文件选择器传入的文件，并按名称、大小、修改时间去重。 */
  function acceptFiles(files: File[]) {
    setUploadFiles((current) => Array.from(new Map(
      // 同名文件仍可能是不同版本，加入大小和最后修改时间后只过滤真正重复的选择。
      [...current, ...files].map((file) => [`${file.name}:${file.size}:${file.lastModified}`, file]),
    ).values()));  // 名称、大小、修改时间组合去重，保留真正版本差异
  }

  /** 提交搜索草稿并回到第一页，避免旧页码超出新结果的总页数。 */
  function search(event: FormEvent) {
    event.preventDefault();
    setPage(1);  // 新搜索回到第一页，避免旧页码超出新结果总页数
    setQuery(queryInput.trim());
  }

  /** 逐个上传队列文件，并把单文件进度折算成整个队列的总体进度。 */
  async function upload() {
    if (!uploadFiles.length) return;
    setBusy("upload"); setError(""); setNotice(""); setUploadProgress(0);
    try {
      for (let index = 0; index < uploadFiles.length; index += 1) {
        const file = uploadFiles[index];
        await uploadLibraryFile(file, uploadScope, uploadDescription, (progress) => {
          // 已完成文件数加当前文件小数进度，再除以总数得到连续的总体百分比。
          setUploadProgress(Math.round(((index + progress / 100) / uploadFiles.length) * 100));
        });
      }
      setNotice(`已上传 ${uploadFiles.length} 个文件。`);
      setUploadFiles([]); setUploadDescription(""); setPage(1);
      // 上传后刷新列表和配额汇总；自增键可在其他筛选参数不变时触发 load。
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "文件上传失败");
    } finally {
      setBusy("");
    }
  }

  /** 把选中文件的可编辑属性复制到弹窗草稿，取消时不会污染列表快照。 */
  function openEdit(file: LibraryFile) {
    setEditFile(file); setEditName(file.name); setEditDescription(file.description); setEditScope(file.scope); setEditCategory(file.category);
  }

  /** 保存文件名、说明、范围和人工业务分类。 */
  async function saveEdit() {
    if (!editFile || !editName.trim()) return;
    setBusy(`edit:${editFile.id}`); setError(""); setNotice("");
    try {
      await updateLibraryFile(editFile.id, { name: editName.trim(), description: editDescription.trim(), scope: editScope, category: editCategory });
      setNotice("文件信息已更新。"); setEditFile(null); setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "文件信息更新失败");
    } finally { setBusy(""); }
  }

  /** 替换文件二进制内容但保留数据库记录、权限、说明和修改历史。 */
  async function replace(file: File) {
    if (!replaceTarget) return;
    // 先复制目标，避免异步请求期间弹窗状态变化导致后续提示引用空对象。
    const target = replaceTarget;
    setBusy(`replace:${target.id}`); setError(""); setNotice("");
    try {
      await replaceLibraryFile(target.id, file, setUploadProgress);
      setNotice(`已替换“${target.name}”的文件内容。`);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "文件替换失败");
    } finally { setBusy(""); setReplaceTarget(null); setUploadProgress(0); }
  }

  /** 将文件移入服务端回收站；恢复与彻底删除由管理员中心负责。 */
  async function remove(file: LibraryFile) {
    if (!window.confirm(`确定将“${file.name}”移入回收站吗？`)) return;
    setBusy(`delete:${file.id}`); setError(""); setNotice("");
    try {
      const result = await deleteLibraryFile(file.id);
      setNotice(result.message); setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "文件删除失败");
    } finally { setBusy(""); }
  }

  /** 通过带身份校验的同源接口下载文件，并在当前行显示互斥状态。 */
  async function download(file: LibraryFile) {
    setBusy(`download:${file.id}`); setError("");
    try { await downloadLibraryFile(file); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "文件下载失败"); }
    finally { setBusy(""); }
  }

  const summary = data?.summary;
  const pagination = data?.pagination;
  // 配额显示最多钳制到 100%，即使服务端暂时超额也不会让进度条越出卡片。
  const quotaPercent = summary?.quota_bytes ? Math.min(100, Math.round(summary.own_bytes / summary.quota_bytes * 100)) : 0;  // 配额进度最多钳制到 100%
  const hasLibraryFilters = Boolean(query || categoryFilter || filter !== "all");
  // 空态按钮复用此重置动作，恢复默认结果并跳回第一页。
  const clearLibraryFilters = () => { setQueryInput(""); setQuery(""); setCategoryFilter(""); setFilter("all"); setPage(1); };

  return <div className="fyt-page fyt-content-container fyt-ops-page fyt-library-page">
    <section className="fyt-library-summary" aria-label="数据库概况">
      <div><span>可见文件</span><strong>{summary?.visible_count || 0}</strong></div>
      <div><span>团队共享</span><strong>{summary?.team_count || 0}</strong></div>
      <div><span>我的文件</span><strong>{summary?.own_count || 0}</strong></div>
      <div className="fyt-library-storage"><span>我的空间</span><strong>{sizeLabel(summary?.own_bytes || 0)}</strong><small>{quotaPercent}% · 上限 {sizeLabel(summary?.quota_bytes || 0)}</small><i><b style={{ width: `${quotaPercent}%` }} /></i></div>
    </section>

    <section className="fyt-library-upload-panel">
      <div
        className={`fyt-library-drop-zone ${dragging ? "dragging" : ""}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => { event.preventDefault(); setDragging(false); acceptFiles(Array.from(event.dataTransfer.files)); }}
      >
        <input ref={uploadInputRef} type="file" multiple onChange={(event) => { acceptFiles(Array.from(event.target.files || [])); event.currentTarget.value = ""; }} />
        <div className="fyt-library-upload-icon"><Icon name="upload" size={20} /></div>
        <div><strong>{uploadFiles.length ? `已选择 ${uploadFiles.length} 个文件` : "上传文件"}</strong><span>{uploadFiles.length ? uploadFiles.map((file) => file.name).join("、") : "拖放文件到这里，或从本机选择"}</span></div>
        <button className="fyt-action-secondary" type="button" onClick={() => uploadInputRef.current?.click()}><Icon name="plus" size={15} />选择文件</button>
      </div>
      <div className="fyt-library-upload-options">
        <label>可见范围<select value={uploadScope} onChange={(event) => setUploadScope(event.target.value as LibraryScope)}><option value="team">团队共享</option><option value="private">仅自己</option></select></label>
        <label>文件说明<input value={uploadDescription} maxLength={500} placeholder="可选" onChange={(event) => setUploadDescription(event.target.value)} /></label>
        <button className="fyt-action-primary" disabled={!uploadFiles.length || Boolean(busy)} onClick={() => void upload()}>{busy === "upload" ? `上传中 ${uploadProgress}%` : "上传到数据库"}<Icon name="upload" size={16} /></button>
      </div>
      {uploadFiles.length ? <div className="fyt-library-upload-queue">{uploadFiles.map((file) => <span key={`${file.name}:${file.size}:${file.lastModified}`}>{file.name}<button type="button" aria-label={`移除 ${file.name}`} onClick={() => setUploadFiles((current) => current.filter((item) => item !== file))}><Icon name="x" size={12} /></button></span>)}<button type="button" onClick={() => setUploadFiles([])}>清空</button></div> : null}
    </section>

    {notice ? <div className="fyt-notice fyt-notice-success">{notice}</div> : null}
    {error ? <div className="fyt-notice fyt-notice-error">{error}</div> : null}

    <section className="fyt-library-table-panel">
      <div className="fyt-library-toolbar">
        <form onSubmit={search}><div className="fyt-library-search"><Icon name="search" size={15} /><input aria-label="搜索数据库文件" value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="搜索文件、说明或上传者" /></div><button className="fyt-action-secondary" type="submit">搜索</button></form>
        <div className="fyt-library-filter"><label>显示范围<select value={filter} onChange={(event) => { setFilter(event.target.value as LibraryFilter); setPage(1); }}><option value="all">全部可见</option><option value="team">团队共享</option><option value="mine">我的文件</option><option value="private">私有文件</option></select></label><label>业务分类<select value={categoryFilter} onChange={(event) => { setCategoryFilter(event.target.value); setPage(1); }}><option value="">全部分类</option>{(data?.categories || []).map((item) => <option value={item.key} key={item.key}>{item.title}{summary?.category_counts?.[item.key] ? `（${summary.category_counts[item.key]}）` : ""}</option>)}</select></label><button className="fyt-action-icon" type="button" title="刷新文件列表" aria-label="刷新文件列表" onClick={() => setRefreshKey((value) => value + 1)}><Icon name="refresh" size={16} /></button></div>
      </div>

      <div className="fyt-library-table-wrap"><table className="fyt-library-table"><thead><tr><th>文件</th><th>业务分类</th><th>权限</th><th>上传者</th><th>最后修改</th><th>大小</th><th>操作</th></tr></thead><tbody>
        {data?.files.map((file) => <tr key={file.id}>
          <td data-label="文件"><div className="fyt-library-file-name"><span><Icon name="file" size={17} /></span><div><strong title={file.name}>{file.name}</strong><small title={file.description}>{file.description || "没有填写说明"}</small></div></div></td>
          <td data-label="业务分类"><div className="fyt-library-category"><strong title={file.category_title}>{file.category_title}</strong>{file.categories.length > 1 ? <small className="fyt-library-category-secondary" title={file.categories.slice(1).map((key) => data?.categories.find((item) => item.key === key)?.title || key).join("、")}>{file.categories.slice(1).map((key) => data?.categories.find((item) => item.key === key)?.title || key).join("、")}</small> : null}<small>{file.confidence >= 100 ? "人工指定" : `自动识别 ${file.confidence}%`}</small></div></td>
          <td data-label="权限"><span className={`fyt-library-scope ${file.scope}`}>{scopeLabel(file.scope)}</span></td>
          <td data-label="上传者"><div className="fyt-library-person"><i>{file.uploader.display_name.slice(0, 1)}</i><span><strong>{file.uploader.display_name}</strong><small>{file.uploader.username}</small></span></div></td>
          <td data-label="最后修改"><div className="fyt-library-updated"><strong>{timeLabel(file.updated_at)}</strong><small>{file.updated_by ? `${file.updated_by.display_name} 更新` : "上传后未修改"}</small></div></td>
          <td data-label="大小">{sizeLabel(file.size)}</td>
          <td data-label="操作"><div className="fyt-library-row-actions"><button title="下载文件" aria-label={`下载 ${file.name}`} disabled={Boolean(busy)} onClick={() => void download(file)}><Icon name="download" size={15} /></button>{file.permissions.can_edit ? <button title="编辑文件信息" aria-label={`编辑 ${file.name}`} disabled={Boolean(busy)} onClick={() => openEdit(file)}><Icon name="edit" size={15} /></button> : null}{file.permissions.can_replace ? <button title="替换文件内容" aria-label={`替换 ${file.name}`} disabled={Boolean(busy)} onClick={() => { setReplaceTarget(file); replaceInputRef.current?.click(); }}><Icon name="upload" size={15} /></button> : null}{file.permissions.can_delete ? <button className="danger" title="移入回收站" aria-label={`删除 ${file.name}`} disabled={Boolean(busy)} onClick={() => void remove(file)}><Icon name="trash" size={15} /></button> : null}</div></td>
        </tr>)}
        {!loading && !data?.files.length ? <tr><td colSpan={7} className="fyt-library-empty"><EmptyState className="fyt-library-empty-content" illustration="empty-library-shelf.webp" illustrationAlt="尚无可见数据库文件的档案架示意" title={hasLibraryFilters ? "没有符合条件的文件" : "数据库还没有文件"} description={hasLibraryFilters ? "可以换一个筛选条件，或清除筛选后重新查看。" : "上传第一份业务资料后，系统会按分类保存并提供给后续流程使用。"} action={<button className={hasLibraryFilters ? "fyt-action-secondary" : "fyt-action-primary"} type="button" onClick={hasLibraryFilters ? clearLibraryFilters : () => uploadInputRef.current?.click()}>{hasLibraryFilters ? "清除筛选" : "选择第一份文件"}<Icon name={hasLibraryFilters ? "refresh" : "upload"} size={15} /></button>} /></td></tr> : null}
        {loading ? <tr><td colSpan={7} className="fyt-library-empty">正在读取数据库文件...</td></tr> : null}
      </tbody></table></div>

      <div className="fyt-library-pagination"><span>共 {pagination?.total || 0} 个文件</span><div><button className="fyt-action-icon" title="上一页" aria-label="上一页" disabled={!pagination || pagination.page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}><Icon name="left" size={16} /></button><strong>第 {pagination?.page || 1} / {pagination?.pages || 1} 页</strong><button className="fyt-action-icon" title="下一页" aria-label="下一页" disabled={!pagination || pagination.page >= pagination.pages || loading} onClick={() => setPage((value) => value + 1)}><Icon name="right" size={16} /></button></div></div>
    </section>

    <input ref={replaceInputRef} className="hidden-file-input" type="file" onChange={(event) => { const file = event.target.files?.[0]; if (file) void replace(file); event.currentTarget.value = ""; }} />
    {editFile ? <div className="fyt-library-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target && !busy) setEditFile(null); }}><section className="fyt-library-dialog" role="dialog" aria-modal="true" aria-labelledby="fyt-library-edit-title"><div className="fyt-library-dialog-head"><div><h2 id="fyt-library-edit-title">编辑文件信息</h2><p>{editFile.uploader.display_name} 上传 · {timeLabel(editFile.created_at)}</p></div><button className="fyt-action-icon" aria-label="关闭编辑" onClick={() => setEditFile(null)}><Icon name="x" size={16} /></button></div><div className="fyt-library-edit-form"><label>文件名<input value={editName} maxLength={180} onChange={(event) => setEditName(event.target.value)} /></label><label>业务分类<select value={editCategory} onChange={(event) => setEditCategory(event.target.value)}>{(data?.categories || []).map((item) => <option value={item.key} key={item.key}>{item.title}</option>)}</select></label><label>可见范围<select value={editScope} onChange={(event) => setEditScope(event.target.value as LibraryScope)}><option value="team">团队共享</option><option value="private">仅自己</option></select></label><label className="wide">文件说明<textarea value={editDescription} maxLength={500} onChange={(event) => setEditDescription(event.target.value)} /></label></div><div className="fyt-library-dialog-actions"><button className="fyt-action-secondary" disabled={Boolean(busy)} onClick={() => setEditFile(null)}>取消</button><button className="fyt-action-primary" disabled={!editName.trim() || !editCategory || Boolean(busy)} onClick={() => void saveEdit()}>{busy === `edit:${editFile.id}` ? "保存中..." : "保存修改"}</button></div></section></div> : null}
  </div>;
}
