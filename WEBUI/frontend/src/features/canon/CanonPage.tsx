import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { projectQueryKeys } from "../../api/queryKeys";
import type { CanonDecisionRecord } from "../../api/types";
import { AppShell } from "../../components/layout/AppShell";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { FieldLabel, TextInput } from "../../components/ui/Field";
import { fetchCanonDecision, fetchCanonDecisions, searchCanonDecisions } from "./canonApi";

const PAGE_SIZE = 50;

export function CanonPage() {
  const { projectId, decisionId } = useParams();
  const project = projectId ?? "";
  const selectedId = decisionId === undefined ? null : positiveId(decisionId);
  const routeValid = decisionId === undefined || selectedId !== null;
  const [searchText, setSearchText] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [records, setRecords] = useState<CanonDecisionRecord[]>([]);
  const previousProject = useRef(project);
  const browseQuery = useQuery({ queryKey: projectQueryKeys.canonDecisions(project, PAGE_SIZE, offset), queryFn: () => fetchCanonDecisions(project, PAGE_SIZE, offset), enabled: routeValid && activeSearch === "" });
  const searchQuery = useQuery({ queryKey: projectQueryKeys.canonDecisionSearch(project, activeSearch, PAGE_SIZE), queryFn: () => searchCanonDecisions(project, activeSearch, PAGE_SIZE), enabled: routeValid && activeSearch !== "" });
  const result = activeSearch === "" ? browseQuery.data : searchQuery.data;
  useEffect(() => { if (previousProject.current === project) return; previousProject.current = project; setSearchText(""); setActiveSearch(""); setOffset(0); setRecords([]); }, [project]);
  useEffect(() => { if (result === undefined) return; setRecords((current) => offset === 0 ? result : [...current, ...result]); }, [offset, result]);
  function submitSearch(event: FormEvent) { event.preventDefault(); setOffset(0); setRecords([]); setActiveSearch(searchText.trim()); }
  function clearSearch() { setSearchText(""); setActiveSearch(""); setOffset(0); setRecords([]); }
  if (decisionId !== undefined && selectedId === null) return <main className="empty-state"><h1>Page not found</h1><p>Choose a valid canon decision.</p></main>;
  return <AppShell projectId={project}><div className={selectedId === null ? "entity-layout" : "entity-layout entity-detail-route"}><section className="entity-list-pane"><div className="page-heading"><div><p className="eyebrow">Canon / History</p><h1>Canon / History</h1></div></div><form className="entity-search" onSubmit={submitSearch}><FieldLabel htmlFor="canon-search">Search canon decisions</FieldLabel><div className="search-row"><TextInput id="canon-search" aria-label="Search canon decisions" role="searchbox" value={searchText} onChange={(event) => setSearchText(event.target.value)} /><Button type="submit">Search</Button>{activeSearch && <Button type="button" variant="secondary" onClick={clearSearch}>Clear</Button>}</div></form>{(browseQuery.isError || searchQuery.isError) && <p role="alert">Unable to load canon history.</p>}{records.length === 0 && (browseQuery.isPending || searchQuery.isPending) && <p role="status">Loading canon history…</p>}{records.length === 0 && !browseQuery.isPending && !searchQuery.isPending && <p>No canon decisions yet.</p>}<div className="record-list">{records.map((record) => <Link className="record-list-item" key={record.id} to={`/projects/${encodeURIComponent(project)}/canon/${record.id}`}><span><strong>{record.summary}</strong><small>{record.reason}</small></span><small>#{record.id}</small></Link>)}</div>{activeSearch === "" && result?.length === PAGE_SIZE && <Button type="button" variant="secondary" onClick={() => setOffset((value) => value + PAGE_SIZE)}>Load more</Button>}</section><section className="entity-detail-pane">{selectedId === null ? <Card><h2>Select a canon decision</h2><p>Choose a decision to inspect its immutable change record.</p></Card> : <CanonDecisionDetail projectId={project} decisionId={selectedId} />}</section></div></AppShell>;
}

function CanonDecisionDetail({ projectId, decisionId }: { projectId: string; decisionId: number }) {
  const query = useQuery({ queryKey: projectQueryKeys.canonDecision(projectId, decisionId), queryFn: () => fetchCanonDecision(projectId, decisionId), retry: false });
  if (query.isError) return <p role="alert">Unable to load canon decision.</p>;
  if (query.isPending || !query.data) return <p role="status">Loading canon decision…</p>;
  const decision = query.data;
  return <><Link className="back-link" to={`/projects/${encodeURIComponent(projectId)}/canon`}>Back to canon history</Link><Card><div className="detail-heading"><div><p className="eyebrow">Canon decision #{decision.id}</p><h2>{decision.summary}</h2></div></div><h3>Reason</h3><p>{decision.reason || "No reason recorded."}</p><h3>Changes</h3>{decision.changes.length === 0 ? <p>No changes recorded.</p> : <div className="record-list">{decision.changes.map((change, index) => <div className="record-list-item" key={`${change.entity_type}-${change.entity_id}-${index}`}><strong>{change.entity_type} #{change.entity_id}</strong><span>{change.action}</span><div className="comparison-grid"><div><h4>Before</h4><pre className="json-block">{JSON.stringify(change.before_payload, null, 2)}</pre></div><div><h4>After</h4><pre className="json-block">{JSON.stringify(change.after_payload, null, 2)}</pre></div></div></div>)}</div>}</Card></>;
}

function positiveId(value: string): number | null { return /^[1-9]\d*$/.test(value) ? Number(value) : null; }
