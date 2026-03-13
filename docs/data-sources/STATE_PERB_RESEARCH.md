# Research Report: State PERB Data

**Project:** State PERB Data
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the third research task is to inventory state Public Employment Relations Boards (PERBs) and the data they publish online. This report covers all 12 states on the list.

## 2. Summary of Findings

There is **no consistency** in how these states make their labor board data available. Each state requires a completely different approach. The states can be grouped into three categories:

- **Modern Portals (Difficult to Automate):** California, Michigan, Washington, Connecticut, and Oregon have modern, searchable web portals, often provided by third-party vendors. While this makes manual searching easy, it presents a significant challenge for automated collection, likely requiring complex, application-specific scrapers to reverse-engineer their internal APIs.
- **Static Lists of Documents (Requires Scraping):** New York, Illinois, Massachusetts, and Pennsylvania all provide data as lists of links to individual documents (likely PDFs) on static HTML pages. This requires building a web scraper to collect the links and then a separate parser for the unstructured documents.
- **Structured Data (Best for Automation):** Minnesota and Ohio are the most promising sources. Ohio provides a single HTML table with all metadata, which is excellent for bulk collection. Minnesota appears to offer CSV downloads and JSON/XML APIs, which would be the gold standard, though the direct links could not be found.

## 3. State-by-State Breakdown

### New York (PERB)
- **Website:** `https://perb.ny.gov/`
- **Conclusion:** Requires a web scraper. Data is behind a paid subscription for full search.

### California (PERB)
- **Website:** `https://perb.ca.gov/`
- **Conclusion:** Complex scraper needed for a modern portal; limited historical data (2019-present).

### Illinois (ILRB)
- **Website:** `https://ilrb.illinois.gov/`
- **Conclusion:** Requires a web scraper. Historical data access is a concern.

### Massachusetts (DLR)
- **Website:** `https://www.mass.gov/orgs/department-of-labor-relations`
- **Conclusion:** Requires a web scraper.

### Ohio (SERB)
- **Website:** `https://serb.ohio.gov/`
- **Conclusion:** The best source for bulk collection. A simple scraper can get all metadata from a single HTML table.

### Pennsylvania (PLRB)
- **Website:** `https://www.dli.pa.gov/labor-law/labor-management-relations/plrb/Pages/default.aspx`
- **Conclusion:** Requires a web scraper.

### Michigan (MERC)
- **Website:** `https://www.michigan.gov/merc`
- **Conclusion:** Complex scraper needed; restricted access to documents. Limited historical data (2018-present).

### Washington (PERC)
- **Website:** `https://perc.wa.gov/`
- **Conclusion:** Rich data source (1976-present), but requires a complex scraper for a third-party portal.

### Minnesota (BMS)
- **Website:** `https://mn.gov/bms/`
- **Conclusion:** **The gold standard.** Offers CSV, JSON, and XML access, but direct links need to be manually retrieved.

### Connecticut (SBLR)
- **Website:** `https://portal.ct.gov/sblr` (main site may be unreliable)
- **Conclusion:** Excellent historical data (1945-present), but requires a complex scraper for a search portal.

### Oregon (ERB)
- **Website:** `https://www.oregon.gov/erb`
- **Conclusion:** Rich data source (1970s-present), but requires a complex scraper for a third-party portal.

---
This concludes the research on state PERB data. The findings indicate that building a unified dataset from these sources will be a complex but feasible task, requiring a portfolio of different scraping and parsing strategies tailored to each state.
---
