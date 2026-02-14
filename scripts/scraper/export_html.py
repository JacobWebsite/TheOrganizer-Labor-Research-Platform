"""Export all web scraper tables to a browsable HTML file."""
import sys, os, html as htmlmod
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

queries = {
    'Profiles (295)': {
        'sql': """SELECT id, union_name, local_number, parent_union, state,
                         website_url, platform, scrape_status, match_status, f_num,
                         section, officers, address, phone, email, facebook
                  FROM web_union_profiles ORDER BY id""",
        'cols': ['ID','Union Name','Local#','Parent','State','Website','Platform',
                 'Scrape Status','Match Status','F-Num','Section','Officers','Address','Phone','Email','Facebook']
    },
    'Employers (160)': {
        'sql': """SELECT we.id, wp.union_name, we.employer_name, we.state, we.sector,
                         we.match_status, we.matched_employer_id, we.confidence_score,
                         we.extraction_method
                  FROM web_union_employers we
                  JOIN web_union_profiles wp ON we.web_profile_id = wp.id
                  ORDER BY we.match_status, we.employer_name""",
        'cols': ['ID','Source Union','Employer Name','State','Sector','Match Status','Matched ID','Confidence','Method']
    },
    'Contracts (120)': {
        'sql': """SELECT wc.id, wp.union_name, wc.employer_name, wc.contract_title,
                         wc.contract_url, wc.expiration_date
                  FROM web_union_contracts wc
                  JOIN web_union_profiles wp ON wc.web_profile_id = wp.id
                  ORDER BY wc.employer_name""",
        'cols': ['ID','Source Union','Employer','Contract Title','Document URL','Expiration']
    },
    'Membership (31)': {
        'sql': """SELECT wm.id, wp.union_name, wp.state, wm.member_count,
                         wm.count_type, wm.member_count_source, wm.as_of_date
                  FROM web_union_membership wm
                  JOIN web_union_profiles wp ON wm.web_profile_id = wp.id
                  ORDER BY wm.member_count DESC""",
        'cols': ['ID','Union Name','State','Members','Type','Source','As Of']
    },
    'News (183)': {
        'sql': """SELECT wn.id, wp.union_name, wn.headline, wn.news_type,
                         wn.date_published
                  FROM web_union_news wn
                  JOIN web_union_profiles wp ON wn.web_profile_id = wp.id
                  ORDER BY wn.date_published DESC NULLS LAST""",
        'cols': ['ID','Source Union','Headline','Type','Published']
    },
    'Scrape Jobs (112)': {
        'sql': """SELECT sj.id, wp.union_name, sj.target_url, sj.status,
                         sj.pages_scraped, sj.duration_seconds,
                         sj.error_message
                  FROM scrape_jobs sj
                  JOIN web_union_profiles wp ON sj.web_profile_id = wp.id
                  ORDER BY sj.status, sj.id""",
        'cols': ['ID','Union','URL','Status','Pages','Duration(s)','Error']
    },
}

def esc(val):
    if val is None:
        return ''
    s = str(val)
    if s.startswith('http'):
        short = s[:60] + ('...' if len(s) > 60 else '')
        return f'<a href="{htmlmod.escape(s)}" target="_blank">{htmlmod.escape(short)}</a>'
    return htmlmod.escape(s)

tabs_html = ''
tables_html = ''

for i, (label, q) in enumerate(queries.items()):
    active = ' active' if i == 0 else ''
    tab_id = f'tab{i}'
    tabs_html += f'<button class="tab{active}" onclick="showTab(\'{tab_id}\', this)">{label}</button>\n'

    cur.execute(q['sql'])
    rows = cur.fetchall()

    display = 'block' if i == 0 else 'none'
    t = f'<div id="{tab_id}" class="tabcontent" style="display:{display}">\n'
    t += f'<div class="count">{len(rows)} rows | Click any column header to sort</div>\n'
    t += '<table>\n<thead><tr>'
    for c in q['cols']:
        t += f'<th>{c}</th>'
    t += '</tr></thead>\n<tbody>\n'
    for row in rows:
        t += '<tr>'
        for val in row:
            t += f'<td>{esc(val)}</td>'
        t += '</tr>\n'
    t += '</tbody></table></div>\n'
    tables_html += t

page = f'''<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>AFSCME Web Scraper Data</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background: #f5f5f5; padding: 16px; }}
h1 {{ margin-bottom: 4px; font-size: 22px; }}
.subtitle {{ color: #666; font-size: 13px; margin-bottom: 12px; }}
.tabs {{ display: flex; gap: 4px; margin-bottom: 0; flex-wrap: wrap; }}
.tab {{ padding: 8px 16px; border: 1px solid #ccc; border-bottom: none; background: #e8e8e8;
        cursor: pointer; border-radius: 6px 6px 0 0; font-size: 14px; font-weight: 500; }}
.tab.active {{ background: #fff; border-bottom: 1px solid #fff; margin-bottom: -1px; z-index: 1; }}
.tab:hover {{ background: #dde; }}
.tabcontent {{ background: #fff; border: 1px solid #ccc; padding: 12px; border-radius: 0 6px 6px 6px;
              overflow-x: auto; max-height: 80vh; overflow-y: auto; }}
.count {{ font-size: 13px; color: #666; margin-bottom: 8px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th {{ background: #f0f0f0; position: sticky; top: 0; z-index: 2; text-align: left;
      padding: 6px 8px; border: 1px solid #ddd; white-space: nowrap; cursor: pointer; user-select: none; }}
th:hover {{ background: #dde; }}
th.asc::after {{ content: ' \\25B2'; font-size: 10px; }}
th.desc::after {{ content: ' \\25BC'; font-size: 10px; }}
td {{ padding: 5px 8px; border: 1px solid #eee; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
tr:nth-child(even) {{ background: #fafafa; }}
tr:hover {{ background: #eef3ff; }}
a {{ color: #0066cc; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
/* Color-code statuses */
.st-green {{ color: #16a34a; font-weight: 600; }}
.st-yellow {{ color: #ca8a04; font-weight: 600; }}
.st-red {{ color: #dc2626; font-weight: 600; }}
.st-blue {{ color: #2563eb; font-weight: 600; }}
.st-gray {{ color: #6b7280; }}
</style>
</head><body>
<h1>AFSCME Web Scraper Data</h1>
<p class="subtitle">295 directory entries | 103 websites scraped | 160 employers | 120 contracts | 31 membership counts | 183 news items</p>
<div class="tabs">{tabs_html}</div>
{tables_html}
<script>
function showTab(id, btn) {{
  document.querySelectorAll('.tabcontent').forEach(e => e.style.display = 'none');
  document.querySelectorAll('.tab').forEach(e => e.classList.remove('active'));
  document.getElementById(id).style.display = 'block';
  btn.classList.add('active');
}}

// Color-code status cells
const statusColors = {{
  'MATCHED_F7_EXACT': 'st-green', 'MATCHED_OSHA_EXACT': 'st-green', 'MATCHED_OLMS': 'st-green',
  'MATCHED_F7_FUZZY': 'st-yellow', 'MATCHED_OSHA_FUZZY': 'st-yellow', 'MATCHED_OLMS_CROSS_STATE': 'st-yellow',
  'UNMATCHED': 'st-red', 'FAILED': 'st-red',
  'EXTRACTED': 'st-blue', 'FETCHED': 'st-blue', 'COMPLETED': 'st-blue',
  'NO_WEBSITE': 'st-gray', 'NO_LOCAL_NUMBER': 'st-gray', 'PENDING_REVIEW': 'st-gray',
}};
document.querySelectorAll('td').forEach(td => {{
  const cls = statusColors[td.textContent.trim()];
  if (cls) td.classList.add(cls);
}});

// Click-to-sort
document.querySelectorAll('th').forEach(th => {{
  th.addEventListener('click', () => {{
    const table = th.closest('table');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.rows);
    const ci = Array.from(th.parentNode.children).indexOf(th);
    const asc = !th.classList.contains('asc');
    th.parentNode.querySelectorAll('th').forEach(h => {{ h.classList.remove('asc','desc'); }});
    th.classList.add(asc ? 'asc' : 'desc');
    rows.sort((a,b) => {{
      let va = a.cells[ci].textContent.trim();
      let vb = b.cells[ci].textContent.trim();
      let na = parseFloat(va.replace(/,/g,'')), nb = parseFloat(vb.replace(/,/g,''));
      if (!isNaN(na) && !isNaN(nb)) return asc ? na-nb : nb-na;
      return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    }});
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>
</body></html>'''

outpath = os.path.join(os.path.dirname(__file__), '..', '..', 'files', 'afscme_scraper_data.html')
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(page)

print(f'Written to {os.path.abspath(outpath)} ({len(page):,} bytes)')
conn.close()
