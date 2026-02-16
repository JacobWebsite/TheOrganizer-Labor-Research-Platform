
import psycopg2
import os
from dotenv import load_dotenv
import pandas as pd

def run_matching_checks():
    """
    Connects to the database and runs a series of cross-database matching checks.
    """
    load_dotenv()
    conn = None
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME", "olms_multiyear"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD")
        )
        cur = conn.cursor()

        results = []

        # --- F7 employers → OSHA ---
        print("Checking: F7 employers → OSHA")
        try:
            cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches;")
            matched_f7_to_osha = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM f7_employers_deduped;")
            total_f7 = cur.fetchone()[0]
            results.append({
                "Connection": "F7 employers → OSHA",
                "Matched": f"{matched_f7_to_osha:,}",
                "Total": f"{total_f7:,}",
                "Match Rate": f"{(matched_f7_to_osha / total_f7 * 100) if total_f7 > 0 else 0:.2f}%"
            })
        except psycopg2.Error as e:
            print(f"  ERROR: {e}")
            conn.rollback()
            results.append({"Connection": "F7 employers → OSHA", "Matched": "ERROR", "Total": "ERROR", "Match Rate": "ERROR"})

        # --- F7 employers → NLRB ---
        print("Checking: F7 employers → NLRB")
        try:
            # This is a proxy - counting F7 employers who appear in the NLRB participant table
            cur.execute("""
                SELECT COUNT(DISTINCT p.matched_employer_id) 
                FROM nlrb_participants p
                WHERE p.matched_employer_id IS NOT NULL;
            """)
            matched_f7_to_nlrb = cur.fetchone()[0]
            # Total F7 is the same as above
            results.append({
                "Connection": "F7 employers → NLRB",
                "Matched": f"{matched_f7_to_nlrb:,}",
                "Total": f"{total_f7:,}",
                "Match Rate": f"{(matched_f7_to_nlrb / total_f7 * 100) if total_f7 > 0 else 0:.2f}%"
            })
        except psycopg2.Error as e:
            print(f"  ERROR: {e}")
            conn.rollback()
            results.append({"Connection": "F7 employers → NLRB", "Matched": "ERROR", "Total": "ERROR", "Match Rate": "ERROR"})
            
        # --- F7 employers → Crosswalk ---
        print("Checking: F7 employers → Crosswalk")
        try:
            cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM corporate_identifier_crosswalk;")
            matched_f7_to_crosswalk = cur.fetchone()[0]
            # Total F7 is the same as above
            results.append({
                "Connection": "F7 employers → Crosswalk",
                "Matched": f"{matched_f7_to_crosswalk:,}",
                "Total": f"{total_f7:,}",
                "Match Rate": f"{(matched_f7_to_crosswalk / total_f7 * 100) if total_f7 > 0 else 0:.2f}%"
            })
        except psycopg2.Error as e:
            print(f"  ERROR: {e}")
            conn.rollback()
            results.append({"Connection": "F7 employers → Crosswalk", "Matched": "ERROR", "Total": "ERROR", "Match Rate": "ERROR"})


        # --- NLRB elections → Known union ---
        print("Checking: NLRB elections → Known union")
        try:
            cur.execute("""
                SELECT COUNT(DISTINCT e.case_number)
                FROM nlrb_elections e
                JOIN nlrb_participants p ON e.case_number = p.case_number
                WHERE p.participant_type = 'Union';
            """)
            nlrb_with_union = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM nlrb_elections;")
            total_nlrb_elections = cur.fetchone()[0]
            results.append({
                "Connection": "NLRB elections → Known union",
                "Matched": f"{nlrb_with_union:,}",
                "Total": f"{total_nlrb_elections:,}",
                "Match Rate": f"{(nlrb_with_union / total_nlrb_elections * 100) if total_nlrb_elections > 0 else 0:.2f}%"
            })
        except psycopg2.Error as e:
            print(f"  ERROR: {e}")
            conn.rollback()
            results.append({"Connection": "NLRB elections → Known union", "Matched": "ERROR", "Total": "ERROR", "Match Rate": "ERROR"})

        # --- Public sector locals → unions_master ---
        print("Checking: Public sector locals → unions_master")
        try:
            cur.execute("SELECT COUNT(DISTINCT f_num) FROM ps_union_locals WHERE f_num IS NOT NULL;")
            ps_locals_matched = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ps_union_locals;")
            total_ps_locals = cur.fetchone()[0]
            results.append({
                "Connection": "Public sector locals → unions_master",
                "Matched": f"{ps_locals_matched:,}",
                "Total": f"{total_ps_locals:,}",
                "Match Rate": f"{(ps_locals_matched / total_ps_locals * 100) if total_ps_locals > 0 else 0:.2f}%"
            })
        except psycopg2.Error as e:
            print(f"  ERROR: {e}")
            conn.rollback()
            results.append({"Connection": "Public sector locals → unions_master", "Matched": "ERROR", "Total": "ERROR", "Match Rate": "ERROR"})

        print("\n--- Match Rate Summary ---")
        if results:
            print(pd.DataFrame(results).to_markdown(index=False))

    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    run_matching_checks()
