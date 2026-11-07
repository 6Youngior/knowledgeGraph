import { useEffect, useState } from 'react';
import { useIsFetching, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { api } from './api';
import type { GraphNode, ViewKey } from './types';
import { Sidebar } from './components/Sidebar';
import { Topbar } from './components/Topbar';
import { DemoOverlay } from './components/DemoOverlay';
import { ResearchView } from './views/ResearchView';
import { CaseLibraryView } from './views/CaseLibraryView';
import { KnowledgeUpdateView } from './views/KnowledgeUpdateView';
import { SourcesMethodsView } from './views/SourcesMethodsView';

export function App() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<ViewKey>('research');
  const [eventId, setEventId] = useState<string | null>(null);
  const [focusTarget, setFocusTarget] = useState<{ node: GraphNode; token: number } | null>(null);
  const [pendingFocusGroup, setPendingFocusGroup] = useState<string | null>(null);
  const [pendingFocusSymbol, setPendingFocusSymbol] = useState<string | null>(null);
  const [demoStep, setDemoStep] = useState<number | null>(null);

  const healthQuery = useQuery({ queryKey: ['health'], queryFn: api.health, retry: 1, refetchInterval: 30000 });
  const overviewQuery = useQuery({ queryKey: ['overview'], queryFn: api.overview, retry: 1 });
  const eventsQuery = useQuery({ queryKey: ['events'], queryFn: api.events, retry: 1 });

  const events = eventsQuery.data?.events ?? [];
  const overview = overviewQuery.data;
  const event = events.find((item) => item.id === eventId) ?? events[0];
  const refreshing = useIsFetching() > 0;

  useEffect(() => {
    if (events.length === 0) return;
    if (!eventId || !events.some((item) => item.id === eventId)) setEventId(events[0].id);
  }, [events, eventId]);

  useEffect(() => {
    // A pending focus belongs to one event; never leak it into another case.
    setPendingFocusGroup(null);
    setPendingFocusSymbol(null);
  }, [eventId]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [view]);

  useEffect(() => {
    const label = view === 'research' ? '事件研究' : view === 'cases' ? '案例库' : view === 'update' ? '知识更新' : '资料与方法';
    document.title = `${label} · FinGraph`;
  }, [view]);

  const startDemo = () => {
    // The scripted walkthrough is explicitly the GLM-5 case; switching is
    // visible to the audience and never resets the user's graph.
    const glm = events.find(
      (item) => item.id === 'event:glm5-release' || /GLM-5/i.test(item.title),
    );
    if (glm) setEventId(glm.id);
    setDemoStep(0);
    setView('research');
  };

  const goDemoStep = (step: number) => {
    setDemoStep(step);
    setView(step === 4 ? 'update' : 'research');
  };

  const offline = healthQuery.isError || (overviewQuery.isError && !overview);

  return (
    <div className={`app-shell ${demoStep !== null ? 'demo-active' : ''}`}>
      <Sidebar
        view={view}
        onNavigate={setView}
        events={events}
        eventId={eventId}
        overview={overview}
        health={healthQuery.data}
      />

      <main className="main">
        <Topbar
          view={view}
          health={healthQuery.data}
          overview={overview}
          onSearchSelect={(node) => {
            setFocusTarget({ node, token: Date.now() });
            setView('research');
          }}
          onRefresh={() => queryClient.invalidateQueries()}
          refreshing={refreshing}
        />

        {offline ? (
          <div className="offline-banner">
            <AlertTriangle size={15} />
            <span>数据服务未连接，请确认后端已启动。</span>
            <button type="button" className="button ghost small" onClick={() => { healthQuery.refetch(); overviewQuery.refetch(); eventsQuery.refetch(); }}>
              <RefreshCw size={13} /> 重试
            </button>
          </div>
        ) : null}

        <div className="content">
          {view === 'research' ? (
            <ResearchView
              events={events}
              eventId={eventId}
              overview={overview}
              demoStep={demoStep}
              pendingFocusGroup={pendingFocusGroup}
              pendingFocusSymbol={pendingFocusSymbol}
              onFocusApplied={() => { setPendingFocusGroup(null); setPendingFocusSymbol(null); }}
              onEventChange={setEventId}
              onStartDemo={startDemo}
              onOpenCases={() => setView('cases')}
              onOpenUpdate={() => setView('update')}
              focusTarget={focusTarget}
            />
          ) : null}

          {view === 'cases' ? (
            <CaseLibraryView
              events={events}
              overview={overview}
              onOpenEvent={(id) => {
                setEventId(id);
                setView('research');
              }}
            />
          ) : null}

          {view === 'update' ? (
            <KnowledgeUpdateView
              overview={overview}
              event={event}
              demoActive={demoStep === 4}
              onNavigateResearch={(focusGroup, focusSymbol) => {
                if (focusGroup) setPendingFocusGroup(focusGroup);
                if (focusSymbol) setPendingFocusSymbol(focusSymbol);
                setDemoStep(null);
                setView('research');
              }}
            />
          ) : null}

          {view === 'sources' ? (
            <SourcesMethodsView
              overview={overview}
              health={healthQuery.data}
              overviewError={overviewQuery.error}
              onRetryOverview={() => overviewQuery.refetch()}
            />
          ) : null}
        </div>

        <footer className="app-footer">
          <span>FinGraph · AI 产业事件关联证券研究</span>
          <span>数据来自知识图谱与本地行情缓存</span>
        </footer>
      </main>

      {demoStep !== null ? (
        <DemoOverlay
          step={demoStep}
          onPrev={() => goDemoStep(Math.max(0, demoStep - 1))}
          onNext={() => goDemoStep(Math.min(4, demoStep + 1))}
          onClose={() => setDemoStep(null)}
        />
      ) : null}
    </div>
  );
}
