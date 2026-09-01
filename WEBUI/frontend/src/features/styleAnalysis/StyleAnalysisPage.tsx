import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, NavLink, useLocation, useNavigate, useParams } from "react-router-dom";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextArea, TextInput } from "../../components/ui/Field";
import { projectQueryKeys } from "../../api/queryKeys";
import {
  activateProfile,
  addCorpusWork,
  analyzeDocument,
  analyzeReferenceWork,
  archiveProfile,
  compareCorpora,
  createCorpus,
  createInferenceReview,
  createManualProfile,
  createOverride,
  createProfileFromCorpus,
  createReviewItem,
  deleteReferenceWork,
  fetchAggregates,
  fetchAnalysisRuns,
  fetchCorpus,
  fetchCorpora,
  fetchLintFindings,
  fetchLintRuns,
  fetchProfile,
  fetchProfiles,
  fetchReferenceEpisodes,
  fetchReferenceWork,
  fetchReferenceWorks,
  fetchReviewItems,
  fetchSemantics,
  importStyleFile,
  ignoreReviewItem,
  recomputeAggregates,
  resolveReviewItem,
  reviewFinding,
  runLint,
} from "./styleAnalysisApi";
import type {
  Aggregate,
  LintFinding,
  LintRun,
  ProfileDetail,
  ReferenceEpisode,
  ReviewItem,
  StyleJob,
} from "./styleAnalysisApi";
import { isTerminalStyleJob, useStyleJobPolling } from "./useStyleJobPolling";

type Section =
  | "overview"
  | "sources"
  | "reference-work"
  | "document"
  | "corpora"
  | "compare"
  | "profiles"
  | "profile"
  | "review"
  | "lint";

function positiveId(value: string | undefined): number | null {
  if (value === undefined) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function sectionForPath(pathname: string): Section {
  if (pathname.endsWith("/sources")) return "sources";
  if (pathname.includes("/reference-works/")) return "reference-work";
  if (pathname.includes("/documents/")) return "document";
  if (pathname.endsWith("/corpora/compare")) return "compare";
  if (pathname.endsWith("/corpora")) return "corpora";
  if (pathname.includes("/profiles/")) return "profile";
  if (pathname.endsWith("/profiles")) return "profiles";
  if (pathname.endsWith("/review")) return "review";
  if (pathname.endsWith("/lint")) return "lint";
  return "overview";
}

function displayError(error: unknown): string {
  return error instanceof Error ? error.message : "読み込みに失敗しました。";
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function StatusBadge({ value }: { value: string | undefined }) {
  return <Badge>{value ?? "unknown"}</Badge>;
}

function QueryState({
  loading,
  error,
  children,
}: {
  loading: boolean;
  error: unknown;
  children: ReactNode;
}) {
  if (loading) return <p role="status">読み込み中…</p>;
  if (error) return <p role="alert">{displayError(error)}</p>;
  return <>{children}</>;
}

function JobProgress({ projectId, jobId }: { projectId: string; jobId: number | null }) {
  const query = useStyleJobPolling(projectId, jobId);
  if (jobId === null) return null;
  if (query.isPending) return <p role="status">Analysis job #{jobId} を取得中…</p>;
  if (query.error) return <p role="alert">Job取得エラー: {displayError(query.error)}</p>;
  const job = query.data;
  if (!job) return null;
  return (
    <div className="style-job-progress" role="status" aria-live="polite">
      <strong>Analysis job #{job.job_id}</strong>
      <StatusBadge value={job.status} />
      {job.progress.current !== null && job.progress.total !== null ? (
        <span>{job.progress.current}/{job.progress.total}</span>
      ) : null}
      {job.error_message ? <p role="alert">{job.error_message}</p> : null}
      {job.warnings.length > 0 ? (
        <ul className="style-warning-list">
          {job.warnings.map((warning, index) => <li key={index}>{String(warning)}</li>)}
        </ul>
      ) : null}
      {isTerminalStyleJob(job.status) && job.status === "succeeded" ? (
        <details>
          <summary>Job result</summary>
          <pre className="json-block">{formatJson(job.result)}</pre>
        </details>
      ) : null}
    </div>
  );
}

function StyleNavigation({ projectId, section }: { projectId: string; section: Section }) {
  const base = `/projects/${encodeURIComponent(projectId)}/style-analysis`;
  const links = [
    ["sources", "Sources"],
    ["corpora", "Corpora / Aggregate"],
    ["profiles", "Profiles"],
    ["review", "Review / Override"],
    ["lint", "Lint"],
  ] as const;
  return (
    <nav className="style-analysis-nav" aria-label="Style analysis sections">
      {links.map(([path, label]) => (
        <NavLink key={path} className={({ isActive }) => isActive ? "detail-tab active" : "detail-tab"} to={`${base}/${path}`}>
          {label}
        </NavLink>
      ))}
      {section === "compare" ? <span className="detail-tab active">Compare</span> : null}
    </nav>
  );
}

function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">Style analysis</p>
        <h1>{title}</h1>
        <p className="helper-text">{description}</p>
      </div>
    </div>
  );
}

function Overview({ projectId }: { projectId: string }) {
  const base = `/projects/${encodeURIComponent(projectId)}/style-analysis`;
  return (
    <>
      <PageHeader title="文体分析" description="参照作品、分析結果、プロファイル、Lintを同じプロジェクト境界で確認します。" />
      <div className="style-analysis-grid">
        <Card><h2>Sources / Reference Work</h2><p>ローカルTXT・HTML・EPUBを取り込み、参照作品として分析します。</p><Link className="back-link" to={`${base}/sources`}>Sourcesを開く</Link></Card>
        <Card><h2>Document Analysis</h2><p>Text revisionとStructure revisionを分けて選び、Basic/Semanticを個別に確認します。</p><p className="helper-text">DocumentはReference WorkのEpisodeから開きます。</p></Card>
        <Card><h2>Corpus / Aggregate / Profile</h2><p>Archivedを除いたCorpusの集計と、保存・Activate前のProfile Versionを管理します。</p><Link className="back-link" to={`${base}/corpora`}>Corporaを開く</Link></Card>
        <Card><h2>Review / Lint</h2><p>ReviewItem、Inference Review、Overrideを分離し、CoverageとFindingを確認します。</p><Link className="back-link" to={`${base}/lint`}>Lintを開く</Link></Card>
      </div>
    </>
  );
}

function SourcesPage({ projectId }: { projectId: string }) {
  const client = useQueryClient();
  const [sourceType, setSourceType] = useState<"text" | "html_file" | "epub">("text");
  const [file, setFile] = useState<File | null>(null);
  const [importResult, setImportResult] = useState<{ reused_existing: boolean; reference_work_id: number; source_id: number } | null>(null);
  const works = useQuery({
    queryKey: projectQueryKeys.styleReferenceWorks(projectId),
    queryFn: () => fetchReferenceWorks(projectId),
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: () => importStyleFile(projectId, sourceType, file as File),
    onSuccess: (result) => {
      setImportResult(result);
      void client.invalidateQueries({ queryKey: projectQueryKeys.styleReferenceWorks(projectId) });
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (file) mutation.mutate();
  }
  return (
    <>
      <PageHeader title="Sources" description="Importはローカルファイルだけを受け付けます。Network URLやRefresh操作はありません。" />
      <Card>
        <h2>Local source import</h2>
        <form className="style-analysis-form" onSubmit={submit}>
          <div className="field-group"><FieldLabel htmlFor="style-source-type">Source type</FieldLabel><select id="style-source-type" className="field-control" value={sourceType} onChange={(event) => setSourceType(event.target.value as typeof sourceType)}><option value="text">TXT</option><option value="html_file">HTML</option><option value="epub">EPUB</option></select></div>
          <div className="field-group"><FieldLabel htmlFor="style-source-file">Local file</FieldLabel><TextInput id="style-source-file" type="file" accept={sourceType === "text" ? ".txt,text/plain" : sourceType === "html_file" ? ".html,.htm,text/html" : ".epub,application/epub+zip"} onChange={(event) => setFile(event.target.files?.[0] ?? null)} required /></div>
          <Button type="submit" disabled={!file || mutation.isPending}>Import</Button>
        </form>
        {mutation.error ? <p role="alert">Importエラー: {displayError(mutation.error)}</p> : null}
        {importResult ? <p role="status">{importResult.reused_existing ? "既存Sourceを再利用しました。" : "新しいSourceを登録しました。"} Reference Work #{importResult.reference_work_id}</p> : null}
      </Card>
      <Card>
        <div className="section-heading"><h2>Reference Works</h2><StatusBadge value={works.data ? `${works.data.length} works` : undefined} /></div>
        <QueryState loading={works.isPending} error={works.error}>
          {works.data?.length ? <div className="record-list">{works.data.map((work) => <Link className="record-list-item" key={work.reference_work_id} to={`/projects/${encodeURIComponent(projectId)}/style-analysis/reference-works/${work.reference_work_id}`}><span><strong>{work.title}</strong><small>{work.author_name ?? "著者不明"} · {work.episode_count} episodes</small></span><StatusBadge value={work.source_type} /></Link>)}</div> : <p className="empty-state">まだReference Workがありません。</p>}
        </QueryState>
      </Card>
    </>
  );
}

function ReferenceWorkPage({ projectId, workId }: { projectId: string; workId: number | null }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [jobId, setJobId] = useState<number | null>(null);
  const work = useQuery({ queryKey: projectQueryKeys.styleReferenceWork(projectId, workId ?? 0), queryFn: () => fetchReferenceWork(projectId, workId as number), enabled: workId !== null, retry: false });
  const episodes = useQuery({ queryKey: projectQueryKeys.styleReferenceEpisodes(projectId, workId ?? 0), queryFn: () => fetchReferenceEpisodes(projectId, workId as number), enabled: workId !== null, retry: false });
  const analyzeMutation = useMutation({ mutationFn: (preset: "deterministic" | "full") => analyzeReferenceWork(projectId, workId as number, preset), onSuccess: (job) => setJobId(job.job_id) });
  const purgeMutation = useMutation({ mutationFn: () => deleteReferenceWork(projectId, workId as number), onSuccess: () => { void client.invalidateQueries({ queryKey: projectQueryKeys.styleReferenceWorks(projectId) }); void navigate(`/projects/${encodeURIComponent(projectId)}/style-analysis/sources`); } });
  if (workId === null) return <p role="alert">Reference Work IDが不正です。</p>;
  return (
    <>
      <Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/style-analysis/sources`}>← Sources</Link>
      <QueryState loading={work.isPending} error={work.error}>
        {work.data ? <>
          <PageHeader title={work.data.title} description={`${work.data.author_name ?? "著者不明"} · ${work.data.source_type}`} />
          <Card>
            <div className="form-actions"><Button onClick={() => analyzeMutation.mutate("deterministic")} disabled={analyzeMutation.isPending}>Deterministic analyze</Button><Button variant="secondary" onClick={() => analyzeMutation.mutate("full")} disabled={analyzeMutation.isPending}>Full analyze</Button><Button variant="danger" onClick={() => { if (window.confirm("このReference Workと配下の分析データをPurgeしますか？")) purgeMutation.mutate(); }} disabled={purgeMutation.isPending}>Purge</Button></div>
            {analyzeMutation.error ? <p role="alert">Analyzeエラー: {displayError(analyzeMutation.error)}</p> : null}
            {purgeMutation.error ? <p role="alert">Purgeエラー: {displayError(purgeMutation.error)}</p> : null}
            <JobProgress projectId={projectId} jobId={jobId} />
          </Card>
          <Card>
            <div className="section-heading"><h2>Episodes</h2><StatusBadge value={`${work.data.episode_count} episodes`} /></div>
            <QueryState loading={episodes.isPending} error={episodes.error}>
              {episodes.data?.map((episode) => <div className="record-list-item" key={episode.reference_episode_id}><span><strong>{episode.order_index}. {episode.title}</strong><small>document {episode.style_document_id ?? "未投影"} · text {episode.current_text_revision_id ?? "-"} · structure {episode.current_structure_revision_id ?? "-"}</small></span><span className="form-actions"><StatusBadge value={episode.analysis_status.basic?.state} />{episode.style_document_id ? <Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/style-analysis/documents/${episode.style_document_id}`}>Document</Link> : null}</span></div>)}
            </QueryState>
          </Card>
        </> : null}
      </QueryState>
    </>
  );
}

async function loadDocumentEpisodes(projectId: string): Promise<ReferenceEpisode[]> {
  const works = await fetchReferenceWorks(projectId);
  const groups = await Promise.all(works.map((work) => fetchReferenceEpisodes(projectId, work.reference_work_id)));
  return groups.flat();
}

function DocumentPage({ projectId, documentId }: { projectId: string; documentId: number | null }) {
  const [jobId, setJobId] = useState<number | null>(null);
  const [preset, setPreset] = useState<"deterministic" | "full">("deterministic");
  const episodes = useQuery({ queryKey: projectQueryKeys.styleAnalysis(projectId, "document-episodes"), queryFn: () => loadDocumentEpisodes(projectId), enabled: documentId !== null, retry: false });
  const episode = episodes.data?.find((item) => item.style_document_id === documentId);
  const runs = useQuery({ queryKey: projectQueryKeys.styleAnalysis(projectId, `document-runs-${documentId ?? 0}`), queryFn: () => fetchAnalysisRuns(projectId, documentId as number), enabled: documentId !== null, retry: false });
  const semantics = useQuery({ queryKey: projectQueryKeys.styleAnalysis(projectId, `semantics-${documentId ?? 0}-${episode?.current_structure_revision_id ?? 0}`), queryFn: () => fetchSemantics(projectId, documentId as number, episode?.current_structure_revision_id as number), enabled: documentId !== null && episode?.current_structure_revision_id !== null && episode?.current_structure_revision_id !== undefined, retry: false });
  const analyzeMutation = useMutation({ mutationFn: () => analyzeDocument(projectId, documentId as number, { text_revision_id: episode?.current_text_revision_id as number, structure_revision_id: episode?.current_structure_revision_id ?? undefined, preset }), onSuccess: (job) => setJobId(job.job_id), });
  const overrideMutation = useMutation({ mutationFn: () => createOverride(projectId, { document_id: documentId, subject_type: "document", subject_id: documentId, field_path: "style.note", operation: "set", value: "manual override", note: "SA-H WebUI" }) });
  const inferenceMutation = useMutation({ mutationFn: (runId: number) => createInferenceReview(projectId, { analysis_run_id: runId, subject_type: "document", subject_id: documentId, field_path: "style.inference", review_status: "confirmed", note: "SA-H WebUI" }) });
  if (documentId === null) return <p role="alert">Document IDが不正です。</p>;
  return (
    <>
      <Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/style-analysis/sources`}>← Sources</Link>
      <PageHeader title={`Document Analysis #${documentId}`} description="Text revision・Structure revision・Basic・Semanticを別々に確認します。Current pointerはAnalyzeの選択で変更しません。" />
      <QueryState loading={episodes.isPending} error={episodes.error}>
        {episode ? <>
          <Card>
            <dl className="record-summary"><div><dt>Episode</dt><dd>{episode.title}</dd></div><div><dt>Current text revision</dt><dd>{episode.current_text_revision_id ?? "未設定"}</dd></div><div><dt>Current structure revision</dt><dd>{episode.current_structure_revision_id ?? "未設定"} ({episode.current_structure_kind ?? "-"})</dd></div><div><dt>Basic status</dt><dd><StatusBadge value={episode.analysis_status.basic?.state} /></dd></div><div><dt>Semantic status</dt><dd><StatusBadge value={episode.analysis_status.semantic?.state} /></dd></div></dl>
            <div className="style-analysis-form"><div className="field-group"><FieldLabel htmlFor="style-document-preset">Analyze preset</FieldLabel><select id="style-document-preset" className="field-control" value={preset} onChange={(event) => setPreset(event.target.value as typeof preset)}><option value="deterministic">Deterministic</option><option value="full">Full (provider required)</option></select></div><Button onClick={() => analyzeMutation.mutate()} disabled={analyzeMutation.isPending || episode.current_text_revision_id === null}>Analyze selected revisions</Button></div>
            {analyzeMutation.error ? <p role="alert">Analyzeエラー: {displayError(analyzeMutation.error)}</p> : null}<JobProgress projectId={projectId} jobId={jobId} />
          </Card>
          <div className="style-analysis-grid">
            <Card><h2>Analysis runs</h2><QueryState loading={runs.isPending} error={runs.error}>{runs.data?.length ? <div className="record-list">{runs.data.map((run) => <div className="record-list-item" key={run.id}><span>#{run.id} {run.analyzer_id} v{run.analyzer_version}</span><StatusBadge value={run.status} /></div>)}</div> : <p>まだAnalysis runがありません。</p>}</QueryState></Card>
            <Card><h2>Semantics</h2><QueryState loading={semantics.isPending} error={semantics.error}>{semantics.data ? <><p>Semantic状態はBasicとは別に表示しています。</p><pre className="json-block">{formatJson({ effective: semantics.data.effective, outputs: semantics.data.outputs })}</pre>{runs.data?.[0] ? <Button variant="secondary" onClick={() => inferenceMutation.mutate(runs.data?.[0].id as number)} disabled={inferenceMutation.isPending}>Confirm inference</Button> : null}{inferenceMutation.error ? <p role="alert">Inference Reviewエラー: {displayError(inferenceMutation.error)}</p> : null}</> : <p>Structure revisionがないためSemantic表示はありません。</p>}</QueryState></Card>
          </div>
          <Card><h2>Corrections</h2><p className="helper-text">OverrideとInference Reviewは別操作です。Authoring Character / World / Canonへの自動書き込みは行いません。</p><div className="form-actions"><Button variant="secondary" onClick={() => overrideMutation.mutate()} disabled={overrideMutation.isPending}>Create manual override</Button></div>{overrideMutation.error ? <p role="alert">Overrideエラー: {displayError(overrideMutation.error)}</p> : null}</Card>
        </> : <p>Document #{documentId}に対応するReference Episodeがありません。</p>}
      </QueryState>
    </>
  );
}

function CorporaPage({ projectId, compare }: { projectId: string; compare: boolean }) {
  const client = useQueryClient();
  const [selectedCorpusId, setSelectedCorpusId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [workId, setWorkId] = useState("");
  const [compareIds, setCompareIds] = useState("");
  const [comparison, setComparison] = useState<unknown>(null);
  const corpora = useQuery({ queryKey: projectQueryKeys.styleCorpora(projectId), queryFn: () => fetchCorpora(projectId), retry: false });
  const works = useQuery({ queryKey: projectQueryKeys.styleReferenceWorks(projectId), queryFn: () => fetchReferenceWorks(projectId), retry: false });
  const detail = useQuery({ queryKey: projectQueryKeys.styleCorpus(projectId, selectedCorpusId ?? 0), queryFn: () => fetchCorpus(projectId, selectedCorpusId as number), enabled: selectedCorpusId !== null, retry: false });
  const aggregates = useQuery({ queryKey: projectQueryKeys.styleAnalysis(projectId, `corpus-aggregates-${selectedCorpusId ?? 0}`), queryFn: () => fetchAggregates(projectId, "corpus", selectedCorpusId as number), enabled: selectedCorpusId !== null, retry: false });
  const createMutation = useMutation({ mutationFn: () => createCorpus(projectId, name, description), onSuccess: () => { setName(""); setDescription(""); void client.invalidateQueries({ queryKey: projectQueryKeys.styleCorpora(projectId) }); } });
  const addMutation = useMutation({ mutationFn: () => addCorpusWork(projectId, selectedCorpusId as number, Number(workId)), onSuccess: () => void client.invalidateQueries({ queryKey: projectQueryKeys.styleCorpus(projectId, selectedCorpusId as number) }) });
  const aggregateMutation = useMutation({ mutationFn: () => recomputeAggregates(projectId, "corpus", selectedCorpusId as number, { measurement_target_type: "document", filter: {}, metric_names: ["sentence_length", "paragraph_length"] }), onSuccess: () => void client.invalidateQueries({ queryKey: projectQueryKeys.styleAnalysis(projectId, `corpus-aggregates-${selectedCorpusId ?? 0}`) }) });
  const compareMutation = useMutation({ mutationFn: () => compareCorpora(projectId, compareIds.split(",").map((item) => Number(item.trim())).filter((item) => item > 0)), onSuccess: setComparison });
  function create(event: FormEvent) { event.preventDefault(); if (name.trim()) createMutation.mutate(); }
  return (
    <>
      <PageHeader title={compare ? "Corpus compare" : "Corpora / Aggregate"} description="CorpusのmembershipとAggregateのfreshnessを明示します。Archivedはデフォルト一覧から除外されます。" />
      <Card><h2>Create corpus</h2><form className="style-analysis-form" onSubmit={create}><div className="field-group"><FieldLabel htmlFor="style-corpus-name">Name</FieldLabel><TextInput id="style-corpus-name" value={name} onChange={(event) => setName(event.target.value)} required /></div><div className="field-group"><FieldLabel htmlFor="style-corpus-description">Description</FieldLabel><TextArea id="style-corpus-description" value={description} onChange={(event) => setDescription(event.target.value)} /></div><Button type="submit" disabled={createMutation.isPending}>Save corpus</Button></form>{createMutation.error ? <p role="alert">Corpus作成エラー: {displayError(createMutation.error)}</p> : null}</Card>
      <div className="style-analysis-grid"><Card><h2>Corpora</h2><QueryState loading={corpora.isPending} error={corpora.error}>{corpora.data?.length ? <div className="record-list">{corpora.data.map((corpus) => <button className="record-list-item" type="button" key={corpus.id} onClick={() => setSelectedCorpusId(corpus.id)}><span><strong>{corpus.name}</strong><small>{corpus.description || "説明なし"}</small></span><StatusBadge value={selectedCorpusId === corpus.id ? "selected" : "saved"} /></button>)}</div> : <p>Corpusがありません。</p>}</QueryState></Card><Card><h2>Selected corpus</h2>{selectedCorpusId === null ? <p>左からCorpusを選択してください。</p> : <><QueryState loading={detail.isPending} error={detail.error}>{detail.data ? <pre className="json-block">{formatJson(detail.data)}</pre> : null}</QueryState><div className="style-analysis-form"><div className="field-group"><FieldLabel htmlFor="style-corpus-work">Add reference work</FieldLabel><select id="style-corpus-work" className="field-control" value={workId} onChange={(event) => setWorkId(event.target.value)}><option value="">選択してください</option>{works.data?.map((work) => <option key={work.reference_work_id} value={work.reference_work_id}>{work.title}</option>)}</select></div><Button onClick={() => addMutation.mutate()} disabled={!positiveId(workId) || addMutation.isPending}>Add work</Button><Button variant="secondary" onClick={() => aggregateMutation.mutate()} disabled={aggregateMutation.isPending}>Recompute aggregates</Button></div><QueryState loading={aggregates.isPending} error={aggregates.error}>{aggregates.data ? <div className="record-list">{aggregates.data.map((aggregate) => <AggregateRow key={aggregate.id} aggregate={aggregate} />)}</div> : null}</QueryState></>}</Card></div>
      {(compare || selectedCorpusId !== null) ? <Card><h2>Compare corpora</h2><p className="helper-text">2〜5個のCorpus IDをカンマ区切りで指定します。</p><div className="inline-field"><FieldLabel htmlFor="style-compare-ids">Corpus IDs</FieldLabel><TextInput id="style-compare-ids" value={compareIds} onChange={(event) => setCompareIds(event.target.value)} placeholder="1,2" /><Button onClick={() => compareMutation.mutate()} disabled={compareIds.split(",").filter((item) => positiveId(item.trim())).length < 2 || compareMutation.isPending}>Compare</Button></div>{compareMutation.error ? <p role="alert">Compareエラー: {displayError(compareMutation.error)}</p> : null}{comparison ? <pre className="json-block">{formatJson(comparison)}</pre> : null}</Card> : null}
    </>
  );
}

function AggregateRow({ aggregate }: { aggregate: Aggregate }) {
  return <div className="record-list-item"><span><strong>{aggregate.metric_name} v{aggregate.metric_version}</strong><small>{aggregate.statistic} · n={aggregate.sample_count} · measurements={aggregate.source_measurement_count}</small></span><span><strong>{aggregate.value_real}</strong> <StatusBadge value={aggregate.stale ? "stale" : "fresh"} /></span></div>;
}

function ProfilesPage({ projectId, profileId }: { projectId: string; profileId: number | null }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [metricName, setMetricName] = useState("sentence_length");
  const [corpusId, setCorpusId] = useState("");
  const [aggregateIds, setAggregateIds] = useState("");
  const profiles = useQuery({ queryKey: projectQueryKeys.styleProfiles(projectId), queryFn: () => fetchProfiles(projectId), retry: false });
  const detail = useQuery({ queryKey: projectQueryKeys.styleProfile(projectId, profileId ?? 0), queryFn: () => fetchProfile(projectId, profileId as number), enabled: profileId !== null, retry: false });
  const manualMutation = useMutation({ mutationFn: () => createManualProfile(projectId, { name, description, rules: [{ target_scope: "document", scope_selector: {}, metric_name: metricName, metric_version: 1, preferred_value: 0, min_value: 0, max_value: 0, weight: 1, enabled: true, severity_policy: "standard" }] }), onSuccess: () => { setName(""); void client.invalidateQueries({ queryKey: projectQueryKeys.styleProfiles(projectId) }); } });
  const corpusMutation = useMutation({ mutationFn: () => { const ids = aggregateIds.split(",").map((item) => Number(item.trim())); return createProfileFromCorpus(projectId, { corpus_id: Number(corpusId), name, description, rules: [{ preferred_aggregate_id: ids[0], min_aggregate_id: ids[1], max_aggregate_id: ids[2] }] }); }, onSuccess: () => void client.invalidateQueries({ queryKey: projectQueryKeys.styleProfiles(projectId) }) });
  const activateMutation = useMutation({ mutationFn: (versionNo: number) => activateProfile(projectId, profileId as number, versionNo), onSuccess: () => void client.invalidateQueries({ queryKey: projectQueryKeys.styleProfiles(projectId) }) });
  const archiveMutation = useMutation({ mutationFn: () => archiveProfile(projectId, profileId as number), onSuccess: () => void client.invalidateQueries({ queryKey: projectQueryKeys.styleProfiles(projectId) }) });
  return (
    <>
      <PageHeader title="Profiles" description="Profileは保存したVersionを確認してからActivateします。Archived profileはLint候補にしません。" />
      <Card><h2>Manual profile</h2><form className="style-analysis-form" onSubmit={(event) => { event.preventDefault(); if (name.trim()) manualMutation.mutate(); }}><div className="field-group"><FieldLabel htmlFor="style-profile-name">Name</FieldLabel><TextInput id="style-profile-name" value={name} onChange={(event) => setName(event.target.value)} required /></div><div className="field-group"><FieldLabel htmlFor="style-profile-description">Description</FieldLabel><TextArea id="style-profile-description" value={description} onChange={(event) => setDescription(event.target.value)} /></div><div className="field-group"><FieldLabel htmlFor="style-profile-metric">Metric</FieldLabel><TextInput id="style-profile-metric" value={metricName} onChange={(event) => setMetricName(event.target.value)} required /></div><Button type="submit" disabled={manualMutation.isPending}>Save draft profile</Button></form>{manualMutation.error ? <p role="alert">Profile作成エラー: {displayError(manualMutation.error)}</p> : null}</Card>
      <Card><h2>From corpus</h2><form className="style-analysis-form" onSubmit={(event) => { event.preventDefault(); const ids = aggregateIds.split(",").filter((item) => positiveId(item.trim())); if (positiveId(corpusId) && ids.length === 3 && name.trim()) corpusMutation.mutate(); }}><div className="field-group"><FieldLabel htmlFor="style-profile-corpus">Corpus ID</FieldLabel><TextInput id="style-profile-corpus" inputMode="numeric" value={corpusId} onChange={(event) => setCorpusId(event.target.value)} /></div><div className="field-group"><FieldLabel htmlFor="style-profile-aggregates">preferred,min,max aggregate IDs</FieldLabel><TextInput id="style-profile-aggregates" value={aggregateIds} onChange={(event) => setAggregateIds(event.target.value)} placeholder="10,11,12" /></div><Button type="submit" disabled={corpusMutation.isPending}>Build from exact aggregates</Button></form>{corpusMutation.error ? <p role="alert">Corpus profileエラー: {displayError(corpusMutation.error)}</p> : null}</Card>
      <div className="style-analysis-grid"><Card><h2>Profile list</h2><QueryState loading={profiles.isPending} error={profiles.error}>{profiles.data?.length ? <div className="record-list">{profiles.data.map((profile) => <Link className="record-list-item" key={profile.id} to={`/projects/${encodeURIComponent(projectId)}/style-analysis/profiles/${profile.id}`}><span><strong>{profile.name}</strong><small>{profile.description || "説明なし"}</small></span><StatusBadge value={profile.status} /></Link>)}</div> : <p>Profileがありません。</p>}</QueryState></Card><Card><h2>Profile detail</h2>{profileId === null ? <p>Profileを選択してください。</p> : <QueryState loading={detail.isPending} error={detail.error}>{detail.data ? <ProfileDetailView detail={detail.data} onActivate={(versionNo) => activateMutation.mutate(versionNo)} onArchive={() => { if (window.confirm("このProfileをArchiveしますか？")) archiveMutation.mutate(); }} /> : null}</QueryState>}</Card></div>
    </>
  );
}

function ProfileDetailView({ detail, onActivate, onArchive }: { detail: ProfileDetail; onActivate: (versionNo: number) => void; onArchive: () => void }) {
  return <><dl className="record-summary"><div><dt>Name</dt><dd>{detail.profile.name}</dd></div><div><dt>Status</dt><dd><StatusBadge value={detail.profile.status} /></dd></div><div><dt>Active version</dt><dd>{detail.profile.active_version_id ?? "未設定"}</dd></div></dl>{detail.versions.map(({ version, rules }) => <div className="record-list-item" key={version.id}><span><strong>Version {version.version_no}</strong><small>{rules.length} rules</small></span><span className="form-actions"><Button variant="secondary" onClick={() => onActivate(version.version_no)} disabled={detail.profile.status === "archived"}>Activate</Button><Button variant="danger" onClick={onArchive} disabled={detail.profile.status === "archived"}>Archive</Button></span></div>)}</>;
}

function ReviewPage({ projectId }: { projectId: string }) {
  const client = useQueryClient();
  const [subjectType, setSubjectType] = useState("scene");
  const [subjectId, setSubjectId] = useState("");
  const [note, setNote] = useState("");
  const items = useQuery({ queryKey: projectQueryKeys.styleReviewItems(projectId, "open"), queryFn: () => fetchReviewItems(projectId, "open"), retry: false });
  const createMutation = useMutation({ mutationFn: () => createReviewItem(projectId, { subject_type: subjectType, subject_id: Number(subjectId), priority: "normal" }), onSuccess: () => void client.invalidateQueries({ queryKey: projectQueryKeys.styleReviewItems(projectId, "open") }) });
  const actionMutation = useMutation({ mutationFn: ({ item, action }: { item: ReviewItem; action: "resolve" | "ignore" }) => action === "resolve" ? resolveReviewItem(projectId, item.id, item.version, note) : ignoreReviewItem(projectId, item.id, item.version, note), onSuccess: () => void client.invalidateQueries({ queryKey: projectQueryKeys.styleReviewItems(projectId, "open") }) });
  return <><PageHeader title="Review / Override" description="ReviewItemのResolve/Ignoreは、OverrideやInference Reviewを暗黙には変更しません。" /><Card><h2>Create manual ReviewItem</h2><form className="style-analysis-form" onSubmit={(event) => { event.preventDefault(); if (positiveId(subjectId)) createMutation.mutate(); }}><div className="field-group"><FieldLabel htmlFor="style-review-subject-type">Subject type</FieldLabel><select id="style-review-subject-type" className="field-control" value={subjectType} onChange={(event) => setSubjectType(event.target.value)}><option value="scene">scene</option><option value="block">block</option><option value="entity">entity</option><option value="term">term</option></select></div><div className="field-group"><FieldLabel htmlFor="style-review-subject-id">Subject ID</FieldLabel><TextInput id="style-review-subject-id" inputMode="numeric" value={subjectId} onChange={(event) => setSubjectId(event.target.value)} /></div><Button type="submit" disabled={!positiveId(subjectId) || createMutation.isPending}>Create ReviewItem</Button></form>{createMutation.error ? <p role="alert">ReviewItem作成エラー: {displayError(createMutation.error)}</p> : null}</Card><Card><h2>Open ReviewItems</h2><div className="field-group"><FieldLabel htmlFor="style-review-note">Resolution note</FieldLabel><TextArea id="style-review-note" value={note} onChange={(event) => setNote(event.target.value)} /></div><QueryState loading={items.isPending} error={items.error}>{items.data?.length ? <div className="record-list">{items.data.map((item) => <div className="record-list-item" key={item.id}><span><strong>#{item.id} {item.reason_code}</strong><small>{item.subject_type} #{item.subject_id} · priority {item.priority} · v{item.version}</small></span><span className="form-actions"><Button variant="secondary" onClick={() => actionMutation.mutate({ item, action: "resolve" })}>Resolve</Button><Button variant="ghost" onClick={() => actionMutation.mutate({ item, action: "ignore" })}>Ignore</Button></span></div>)}</div> : <p>Open ReviewItemはありません。</p>}</QueryState>{actionMutation.error ? <p role="alert">Review更新エラー: {displayError(actionMutation.error)}</p> : null}</Card></>;
}

function LintPage({ projectId }: { projectId: string }) {
  const client = useQueryClient();
  const [documentId, setDocumentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [scope, setScope] = useState<"document" | "scene">("document");
  const [jobId, setJobId] = useState<number | null>(null);
  const [lintRunId, setLintRunId] = useState<number | null>(null);
  const episodes = useQuery({ queryKey: projectQueryKeys.styleAnalysis(projectId, "lint-episodes"), queryFn: () => loadDocumentEpisodes(projectId), retry: false });
  const profiles = useQuery({ queryKey: projectQueryKeys.styleProfiles(projectId), queryFn: () => fetchProfiles(projectId), retry: false });
  const selectedEpisode = episodes.data?.find((item) => String(item.style_document_id) === documentId);
  const selectedProfile = profiles.data?.find((item) => String(item.id) === profileId);
  const runs = useQuery({ queryKey: projectQueryKeys.styleLintRuns(projectId, positiveId(documentId) ?? undefined), queryFn: () => fetchLintRuns(projectId, positiveId(documentId) ?? undefined), enabled: Boolean(documentId), retry: false });
  const jobQuery = useStyleJobPolling(projectId, jobId);
  const resultLintId = jobQuery.data?.result.lint_run_id;
  const activeLintId = lintRunId ?? (typeof resultLintId === "number" ? resultLintId : null);
  const findings = useQuery({ queryKey: projectQueryKeys.styleLintFindings(projectId, activeLintId ?? 0), queryFn: () => fetchLintFindings(projectId, activeLintId as number), enabled: activeLintId !== null, retry: false });
  const lintMutation = useMutation({ mutationFn: () => runLint(projectId, Number(documentId), { text_revision_id: selectedEpisode?.current_text_revision_id as number, structure_revision_id: selectedEpisode?.current_structure_revision_id as number, profile_id: Number(profileId), profile_version_no: selectedProfile?.active_version_id ?? 1, ...(scope === "scene" && positiveId(sceneId) ? { scene_id: Number(sceneId) } : {}) }), onSuccess: (job: StyleJob) => { setJobId(job.job_id); setLintRunId(null); } });
  const reviewMutation = useMutation({ mutationFn: ({ finding, status }: { finding: LintFinding; status: "acknowledged" | "ignored" }) => reviewFinding(projectId, finding.id, status, status === "acknowledged" ? "確認済み" : "対象外"), onSuccess: () => void client.invalidateQueries({ queryKey: projectQueryKeys.styleLintFindings(projectId, activeLintId ?? 0) }) });
  const selectedRun = runs.data?.find((run) => run.id === activeLintId) ?? (activeLintId === null ? null : null);
  useEffect(() => { if (typeof resultLintId === "number") setLintRunId(resultLintId); }, [resultLintId]);
  return <><PageHeader title="Lint" description="Document/Scene scopeを選択し、Job polling後にCoverage・Stale・Finding・Evidenceを確認します。Coverage 0は正常な結果として表示します。" /><Card><h2>Run lint</h2><div className="style-analysis-form"><div className="field-group"><FieldLabel htmlFor="style-lint-document">Document</FieldLabel><select id="style-lint-document" className="field-control" value={documentId} onChange={(event) => setDocumentId(event.target.value)}><option value="">選択してください</option>{episodes.data?.filter((episode) => episode.style_document_id !== null).map((episode) => <option key={episode.style_document_id} value={episode.style_document_id as number}>{episode.title} (#{episode.style_document_id})</option>)}</select></div><div className="field-group"><FieldLabel htmlFor="style-lint-profile">Profile</FieldLabel><select id="style-lint-profile" className="field-control" value={profileId} onChange={(event) => setProfileId(event.target.value)}><option value="">選択してください</option>{profiles.data?.filter((profile) => profile.status !== "archived").map((profile) => <option key={profile.id} value={profile.id}>{profile.name} ({profile.status})</option>)}</select></div><div className="field-group"><FieldLabel htmlFor="style-lint-scope">Scope</FieldLabel><select id="style-lint-scope" className="field-control" value={scope} onChange={(event) => setScope(event.target.value as typeof scope)}><option value="document">Document</option><option value="scene">Scene</option></select></div>{scope === "scene" ? <div className="field-group"><FieldLabel htmlFor="style-lint-scene">Scene ID</FieldLabel><TextInput id="style-lint-scene" inputMode="numeric" value={sceneId} onChange={(event) => setSceneId(event.target.value)} /></div> : null}<Button onClick={() => lintMutation.mutate()} disabled={!selectedEpisode?.current_text_revision_id || !selectedEpisode.current_structure_revision_id || !positiveId(documentId) || !positiveId(profileId) || (scope === "scene" && !positiveId(sceneId)) || lintMutation.isPending}>Run lint</Button></div>{lintMutation.error ? <p role="alert">Lint開始エラー: {displayError(lintMutation.error)}</p> : null}<JobProgress projectId={projectId} jobId={jobId} /></Card><Card><h2>Lint result</h2><QueryState loading={runs.isPending} error={runs.error}>{selectedRun || activeLintId ? <LintSummary run={selectedRun} job={jobQuery.data} /> : <p>Lintを実行すると結果が表示されます。</p>}</QueryState>{findings.error ? <p role="alert">Finding取得エラー: {displayError(findings.error)}</p> : null}{findings.data?.map((finding) => <FindingCard key={finding.id} finding={finding} onReview={(status) => reviewMutation.mutate({ finding, status })} />)}</Card></>;
}

function LintSummary({ run, job }: { run: LintRun | null; job: StyleJob | undefined }) {
  const result = job?.result ?? {};
  const coverage = run?.coverage_ratio ?? (typeof result.coverage_ratio === "number" ? result.coverage_ratio : null);
  return <div className="style-analysis-summary"><div><span className="metric-label">Status</span><strong>{run?.status ?? job?.status ?? "queued"}</strong></div><div><span className="metric-label">Coverage</span><strong>{coverage === null ? "-" : coverage}</strong></div><div><span className="metric-label">Stale</span><strong>{run ? String(run.stale) : "-"}</strong></div><div><span className="metric-label">Warnings</span><strong>{run?.warnings.length ?? job?.warnings.length ?? 0}</strong></div></div>;
}

function FindingCard({ finding, onReview }: { finding: LintFinding; onReview: (status: "acknowledged" | "ignored") => void }) {
  return <article className="style-finding-card"><div className="section-heading"><h3>{finding.metric_name}: {finding.observed_value}</h3><StatusBadge value={finding.review_status ?? finding.severity} /></div><p>{finding.explanation_code} · expected {finding.expected_min}〜{finding.expected_max} · deviation {finding.deviation}</p><details><summary>Evidence</summary><pre className="json-block">{formatJson(finding.evidence)}</pre></details><div className="form-actions"><Button variant="secondary" onClick={() => onReview("acknowledged")}>Acknowledge</Button><Button variant="ghost" onClick={() => onReview("ignored")}>Ignore</Button></div></article>;
}

export function StyleAnalysisPage() {
  const { projectId, workId: workIdParam, documentId: documentIdParam, profileId: profileIdParam } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const project = projectId ?? "";
  const section = sectionForPath(location.pathname);
  useEffect(() => {
    if (section === "overview" && project) navigate(`/projects/${encodeURIComponent(project)}/style-analysis/sources`, { replace: true });
  }, [navigate, project, section]);
  const routeIds = useMemo(() => ({ workId: positiveId(workIdParam), documentId: positiveId(documentIdParam), profileId: positiveId(profileIdParam) }), [documentIdParam, profileIdParam, workIdParam]);
  if (!project) return <p role="alert">Project IDがありません。</p>;
  let content: ReactNode;
  if (section === "sources") content = <SourcesPage projectId={project} />;
  else if (section === "reference-work") content = <ReferenceWorkPage projectId={project} workId={routeIds.workId} />;
  else if (section === "document") content = <DocumentPage projectId={project} documentId={routeIds.documentId} />;
  else if (section === "corpora") content = <CorporaPage projectId={project} compare={false} />;
  else if (section === "compare") content = <CorporaPage projectId={project} compare />;
  else if (section === "profiles" || section === "profile") content = <ProfilesPage projectId={project} profileId={routeIds.profileId} />;
  else if (section === "review") content = <ReviewPage projectId={project} />;
  else if (section === "lint") content = <LintPage projectId={project} />;
  else content = <Overview projectId={project} />;
  return <AppShell projectId={project}><div className="style-analysis-page"><StyleNavigation projectId={project} section={section} />{content}</div></AppShell>;
}
