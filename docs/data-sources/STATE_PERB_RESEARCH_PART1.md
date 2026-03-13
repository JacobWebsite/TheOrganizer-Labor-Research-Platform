# Research Report: State PERB Data (Part 1)

**Project:** State PERB Data
**Date:** February 17, 2026
**Author:** Gemini

## 1. Research Question

As per the `GEMINI_RESEARCH_HANDOFF.md` document, the third research task is to inventory state Public Employment Relations Boards (PERBs) and the data they publish online. This report covers the first ten states on the list.

## 2. Summary of Findings

There is **no consistency** in how these states make their labor board data available. Each state requires a completely different approach. The states can be grouped into three categories:

- **Modern Portals (Difficult to Automate):** California, Michigan, Washington, and Connecticut have modern, searchable web portals. While this makes manual searching easy, it presents a significant challenge for automated collection, likely requiring complex, application-specific scrapers to reverse-engineer their internal APIs.
- **Static Lists of Documents (Requires Scraping):** New York, Illinois, Massachusetts, and Pennsylvania all provide data as lists of links to individual documents (likely PDFs) on static HTML pages. This requires building a web scraper to collect the links and then a separate parser for the unstructured documents.
- **Structured Data (Best for Automation):** Minnesota and Ohio are the most promising sources. Ohio provides a single HTML table with all metadata, which is excellent for bulk collection. Minnesota appears to offer CSV downloads and JSON/XML APIs, which would be the gold standard, though the direct links could not be found.

## 3. State-by-State Breakdown

### New York (PERB)
- **Website:** `https://perb.ny.gov/`
- **Searchable Database:** No (publicly accessible).
- **Conclusion:** Requires a web scraper.

### California (PERB)
- **Website:** `https://perb.ca.gov/`
- **Searchable Database:** Yes, the **ePERB Portal**.
- **Time Period:** Late 2019 - present.
- **Conclusion:** Complex scraper needed; limited historical data.

### Illinois (ILRB)
- **Website:** `https://ilrb.illinois.gov/`
- **Searchable Database:** No.
- **Conclusion:** Requires a web scraper. Historical data access is a concern.

### Massachusetts (DLR)
- **Website:** `https://www.mass.gov/orgs/department-of-labor-relations`
- **Searchable Database:** No.
- **Conclusion:** Requires a web scraper.

### Ohio (SERB)
- **Website:** `https://serb.ohio.gov/`
- **Searchable Database:** No, but all metadata is in a single HTML table.
- **Conclusion:** The best source for bulk collection found so far.

### Pennsylvania (PLRB)
- **Website:** `https://www.dli.pa.gov/labor-law/labor-management-relations/plrb/Pages/default.aspx`
- **Searchable Database:** No.
- **Conclusion:** Requires a web scraper.

### Michigan (MERC)
- **Website:** `https://www.michigan.gov/merc`
- **Searchable Database:** Yes, the **MERC e-FILE** system.
- **Time Period:** Late 2018 - present.
- **Conclusion:** Complex scraper needed; restricted access to documents.

### Washington (PERC)
- **Website:** `https://perc.wa.gov/`
- **Searchable Database:** Yes, a third-party portal from Lexum.
- **Time Period:** 1976 - present.
- **Conclusion:** Rich data source, but requires a complex scraper.

### Minnesota (BMS)
- **Website:** `https://mn.gov/bms/`
- **API/Bulk Download:** **Yes.** The website explicitly mentions a **"Awards CSV File"**, **"JSON Search"**, and **"XML Search"**.
- **Conclusion:** **The gold standard.** Most promising source, but direct links need to be manually retrieved from the website.

### Connecticut (SBLR)
- **Website:** `https://portal.ct.gov/sblr` (main site may be unreliable)
- **Searchable Database:** Yes, a searchable database for full-text decisions.
- **Time Period:** 1945 - present.
- **Conclusion:** Excellent historical data, but requires a complex scraper for the search portal.

---
This concludes the first part of the research on state PERB data.
---
