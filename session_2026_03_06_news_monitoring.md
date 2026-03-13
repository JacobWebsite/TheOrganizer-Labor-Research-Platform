# News Monitoring Planning Session (2026-03-06)

## Status: PLANNING (not started)

## Decision: Cost-Conscious Architecture

User rejected scheduled Crawl4AI crawling and per-article Gemini extraction as too expensive.

### Agreed Approach: RSS + Research Piggyback

1. **RSS feeds only** -- Many union sites (especially WordPress) publish RSS/Atom feeds. Parse with free HTTP GET + XML. No Crawl4AI browser sessions needed.

2. **Research agent piggyback** -- When research agent already runs for an employer (user-triggered), save any news it finds as a side effect. Zero extra Gemini cost.

3. **Keyword classification (regex)** -- Use existing `extract_news()` labor keyword list for news_type tagging (strike/organizing/contract/etc). No Gemini extraction on articles.

4. **Our own RSS output** -- API endpoint generates RSS 2.0 XML from collected articles, filterable by union/state/type.

### Tables Needed

- `labor_news_articles` -- article record (URL, headline, summary, source union, date, news_type)
- `labor_news_events` -- structured events matched to DB employers (may defer)
- `news_crawl_runs` -- crawl job tracking

### Flow

```
Union RSS/Atom feeds           Research Agent (already running)
(free HTTP GET + XML parse)         |
        |                     Save news mentions as side effect
        v                           |
  labor_news_articles  <------------+
  (headline, URL, date, union)
        |
  Keyword classification (regex, free)
        |
        v
  news_type tag
        |
        v
  /api/news/rss  (our aggregated feed)
```

### Open Questions

- How many of the 103 AFSCME sites are WordPress (likely have RSS feeds)?
- RSS crawl frequency: every 2 days proposed, but could be less frequent
- Research agent hook: save news from Gemini web search grounding results
- Frontend: news tab per union? Separate news page?
- Event extraction: defer `labor_news_events` table until articles are flowing?

### Existing Infrastructure

- `web_union_news` table exists but tied to union website profiles (not external news)
- `extract_news()` in `scripts/scraper/extract_union_data.py` -- regex keyword classifier
- 12 curated news sources in `.claude/skills/union-research/references/news-sources.md`
- Crawl4AI integrated (but too expensive for scheduled use)
- WordPress detection already exists in scraper (probes `/wp-json/wp/v2/`)
- Roadmap: TASK 8-6 (line 2029 in roadmap)

### Next Steps When Resuming

1. Check how many scraped union sites have RSS feeds (WordPress detection)
2. Create tables
3. Build RSS feed parser script
4. Add research agent news hook
5. Build RSS output API endpoint
