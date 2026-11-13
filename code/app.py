"""FinGraph local research dashboard API and production frontend host."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from graph_store import GraphStore
from extraction import ExtractionService
from market import MarketData
from research import ResearchService
from financial_tools import FinancialResearch
from quant_tools import QuantResearch

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class ExtractRequest(BaseModel):
    sample_id: str | None = None
    text: str | None = Field(default=None, max_length=16000)
    title: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=2000)
    mode: Literal["auto", "live", "replay"] = "auto"


class IngestRequest(BaseModel):
    extraction_id: str


class BriefRequest(BaseModel):
    as_of: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


def create_app(data_dir: Path | None = None, persist=True):
    application = FastAPI(title="FinGraphAgent", version="0.2.0",
                          description="人工智能产业股票的金融分析、知识图谱与量化研究。")
    store = GraphStore(data_dir or ROOT / "data", persist=persist)
    market = MarketData(store.data_dir)
    extraction = ExtractionService(store, ROOT)
    research = ResearchService(store, market)
    application.state.store = store
    application.state.extraction = extraction
    application.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                               allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @application.exception_handler(KeyError)
    async def not_found(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": str(exc.args[0])})

    @application.exception_handler(ValueError)
    async def invalid(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.get("/api/health")
    def health():
        capability = extraction.capability()
        return {"status": "ok", "engine": "NetworkX · typed property graph", "version": "0.2.0",
                "llm_available": capability["available"], "llm_provider": capability["provider"]}

    @application.get("/api/overview")
    def overview():
        return {**store.overview(), "llm": extraction.capability()}

    @application.get("/api/events")
    def events():
        return {"events": list(store.events.values())}

    @application.get("/api/finance")
    def finance_overview(as_of: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return FinancialResearch(store.data_dir / "finance", as_of).overview()

    @application.get("/api/quant")
    def quant_results(view: Literal["overview", "ranking", "backtest"] = "ranking",
                      limit: int = Query(default=10, ge=1, le=50),
                      as_of: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return QuantResearch(store.data_dir / "quant" / "baseline.json", as_of).analyze(view, limit, include_curve=True)

    @application.get("/api/finance/{symbol}")
    def financial_reports(symbol: str, periods: int = Query(default=4, ge=1, le=8),
                          as_of: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return FinancialResearch(store.data_dir / "finance", as_of).company_financials(symbol, periods)

    @application.get("/api/research")
    def research_overview():
        return research.overview()

    @application.get("/api/research/{event_id}")
    def research_detail(event_id: str, as_of: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return research.detail(event_id, as_of)

    @application.post("/api/research/{event_id}/brief")
    def research_brief(event_id: str, body: BriefRequest):
        return research.brief(event_id, body.as_of)

    @application.get("/api/graph")
    def graph(event_id: str | None = None, q: str | None = Query(default=None, max_length=200),
              relation_group: str | None = None, as_of: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return store.query_graph(event_id, q, relation_group, as_of)

    @application.get("/api/events/{event_id}")
    def event_detail(event_id: str, as_of: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return store.event_detail(event_id, as_of)

    @application.get("/api/stocks/related")
    def related(event_id: str | None = None, as_of: str | None = None):
        return {"stocks": store.related_stocks(event_id, as_of)}

    @application.get("/api/market/{symbol}")
    def market_window(symbol: str, event_id: str | None = None, window: int = Query(default=5, ge=1, le=20),
                      as_of: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
        return market.event_window(symbol, store.event(event_id), window, as_of)

    @application.get("/api/sources")
    def sources():
        return {"sources": list(store.sources.values())}

    @application.get("/api/sources/{source_id}")
    def source(source_id: str):
        if source_id not in store.sources:
            raise KeyError("来源不存在")
        return store.sources[source_id]

    @application.get("/api/extraction/samples")
    def samples():
        return {"samples": extraction.public_samples()}

    @application.post("/api/extract")
    def extract(body: ExtractRequest):
        if body.url and urlparse(body.url).scheme not in {"http", "https"}:
            raise ValueError("来源链接必须是 http 或 https URL")
        try:
            return extraction.extract(**body.model_dump())
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.post("/api/ingest")
    def ingest(body: IngestRequest):
        return extraction.ingest(body.extraction_id)

    @application.post("/api/reset")
    def reset():
        return store.reset()

    # Static mount follows API routes, so unknown /api URLs are never swallowed by SPA HTML.
    dist = ROOT / "visualization" / "dist"
    application.mount("/assets", StaticFiles(directory=dist / "assets", check_dir=False), name="assets")

    @application.get("/")
    def index():
        if not (dist / "index.html").exists():
            return HTMLResponse("<h1>FinGraph</h1><p>前端尚未构建，请在 visualization 中执行 npm ci 与 npm run build。</p>", status_code=503)
        return FileResponse(dist / "index.html")

    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("FINGRAPH_PORT", "8000")))
