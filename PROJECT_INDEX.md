# Project Index: Labor Data Project

This document provides a comprehensive index of the files and directories in the Labor Data Project. It is intended to be a starting point for understanding, reorganizing, and consolidating the project.

## Project Overview

The Labor Data Project is a sophisticated data analysis platform designed to help union organizers make strategic decisions. It integrates data from a wide variety of sources, including government databases (OSHA, NLRB, WHD, etc.), commercial datasets (Mergent), and public filings (IRS 990, SEC EDGAR).

The platform's key features include:

*   **A comprehensive database**: A PostgreSQL database that consolidates data from over 10 different sources.
*   **A powerful matching engine**: A multi-tiered matching pipeline that links employers and unions across different datasets.
*   **An organizing scorecard**: A 9-factor scoring system that ranks potential organizing targets.
*   **A FastAPI backend**: A modular and well-tested API for serving the data.
*   **An interactive frontend**: A web-based interface for exploring the data.

The project is well-documented and has a strong focus on data quality and validation. It has undergone multiple rounds of audits and has a comprehensive test suite.

## Directory Structure

The project is organized into the following directories:

*   **`api`**: The FastAPI backend, with a modular structure for routers, models, and middleware.
*   **`data`**: Raw and processed data files, including CSVs, SQLite databases, and JSON files.
*   **`docs`**: A comprehensive collection of documentation, including audit reports, roadmaps, case studies, and methodology documents.
*   **`files`**: The frontend files, including the main HTML file, CSS, and JavaScript.
*   **`logs`**: JSON logs from the validation scripts.
*   **`output`**: Output files from various analysis scripts, including CSVs and HTML reports.
*   **`reports`**: Audit reports and other summary documents.
*   **`scripts`**: A large collection of Python scripts for ETL, matching, scoring, and analysis.
*   **`sql`**: SQL scripts for defining the database schema and creating views.
*   **`src`**: Core, reusable Python and SQL code.
*   **`tests`**: A comprehensive test suite covering the API, data integrity, matching, and scoring.

## File Index

### Root Directory

*   **`.env` / `.env.example`**: Environment variable files for configuring the application.
*   **`pyproject.toml` / `requirements.txt`**: Python project and dependency management files.
*   **`README.md`**: The main README file for the project.
*   **Numerous `.md` files**: A large collection of documentation, including audit reports, roadmaps, and meeting notes. See the `docs` directory for a more organized collection of documentation.
*   **Numerous `.py` files**: A collection of Python scripts, most of which seem to be related to data analysis and quality checks. See the `scripts` directory for a more organized collection of scripts.
*   **Numerous `.sql` files**: A few SQL scripts, mostly for ad-hoc queries. See the `sql` directory for the main schema definitions.

### `api` Directory

*   **`main.py`**: The main entry point for the FastAPI application.
*   **`config.py`**: Application configuration.
*   **`database.py`**: Database connection pool management.
*   **`helpers.py`**: Shared helper functions.
*   **`middleware/`**: Middleware for authentication, rate limiting, and logging.
*   **`models/`**: Pydantic models for the API.
*   **`routers/`**: A collection of FastAPI routers, each handling a specific domain (e.g., `employers.py`, `unions.py`, `organizing.py`).

### `data` Directory

*   **`bls/`**: BLS data files.
*   **`crosswalk/`**: SQLite database for a union crosswalk.
*   **`f7/`**: SQLite database for deduplicated F-7 employers.
*   **`nlrb/`**: SQLite database for NLRB data.
*   **`olms/`**: SQLite database for OLMS union data.
*   **`raw/`**: Raw data files.
*   **`unionstats/`**: Unionstats.com data.
*   **Numerous `.csv`, `.xlsx`, `.json` files**: A mix of raw data, processed data, and analysis output.

### `docs` Directory

*   A comprehensive collection of documentation, including:
    *   **Audit reports**: Detailed reports from multiple rounds of audits by different AI agents.
    *   **Roadmaps**: Several versions of the project roadmap, outlining the development plan.
    *   **Case studies**: In-depth analysis of specific organizing campaigns or data sources.
    *   **Methodology documents**: Detailed explanations of the project's data processing, matching, and scoring methodologies.

### `files` Directory

*   **`organizer_v5.html`**: The main HTML file for the frontend.
*   **`css/`**: CSS files for the frontend.
*   **`js/`**: JavaScript files for the frontend.

### `logs` Directory

*   JSON logs from the validation scripts.

### `output` Directory

*   A large collection of CSV and HTML files, which are likely the output of various analysis scripts.

### `reports` Directory

*   **`database_audit_report.md`**: A detailed audit report of the project's PostgreSQL database.

### `scripts` Directory

*   A large and well-organized collection of Python scripts for various tasks, including:
    *   **`etl/`**: ETL scripts for loading and processing data from various sources.
    *   **`matching/`**: Scripts for matching employers and unions across different datasets.
    *   **`scoring/`**: Scripts for calculating the organizing scorecard.
    *   **`analysis/`**: Scripts for performing various data analyses.
    *   **And many more...**

### `sql` Directory

*   **`schema/`**: A collection of SQL scripts for defining the database schema for different data sources.
*   **`queries/`**: SQL queries for ad-hoc analysis.
*   **`bls/`**: SQL scripts related to BLS data.
*   **`deduplication_views.sql`**: SQL views for analyzing deduplicated union membership data.
*   **`f7_indexes.sql`**: SQL script for creating indexes on the F-7 tables.
*   **`f7_schema.sql`**: The main schema definition for the F-7 data integration.

### `src` Directory

*   **`python/`**: Core, reusable Python code, including name normalization functions.
*   **`sql/`**: Core SQL schema definitions.

### `tests` Directory

*   A comprehensive test suite with a good mix of integration tests, data integrity tests, and unit tests.
    *   **`test_api.py`**: Integration tests for the API endpoints.
    *   **`test_data_integrity.py`**: Tests for data quality and consistency.
    *   **`test_matching.py`**: Unit tests for the matching pipeline.
    *   **`test_scoring.py`**: Unit tests for the scoring engine.

## Recommendations for Reorganization and Consolidation

This project is a treasure trove of data and analysis, but its organization could be improved to make it more accessible and maintainable. Here are some recommendations:

1.  **Consolidate the Roadmaps**: There are multiple roadmap documents. These should be consolidated into a single, living document that is regularly updated. The `Roadmap_TRUE_02_15.md` seems to be the most recent and comprehensive, and it could serve as the basis for this consolidation.
2.  **Organize the Root Directory**: The root directory is cluttered with a large number of files. These should be moved to more appropriate subdirectories. For example:
    *   All documentation files should be moved to the `docs` directory.
    *   All scripts should be moved to the `scripts` directory.
    *   All data files should be moved to the `data` directory.
3.  **Clarify the Role of the `src` Directory**: The `src` directory's purpose is not immediately clear. It seems to contain some core, reusable code, but the bulk of the project's code is in the `api` and `scripts` directories. The project should adopt a more standard Python project structure, with a single `src` directory containing all the application's source code.
4.  **Create a Data Dictionary**: The project has a complex database schema with over 150 tables. A data dictionary that documents each table and column would be invaluable for new developers and analysts. The existing schema files in the `sql/schema` directory are a good starting point for this.
5.  **Document the Data Pipelines**: The `scripts/etl` directory contains a large number of ETL scripts. A document that explains the data flow and the dependencies between these scripts would be very helpful. The `unified_employer_osha_pipeline.py` script is a good example of a complex pipeline that would benefit from more detailed documentation.

By implementing these recommendations, the project will be more organized, easier to understand, and more maintainable in the long run.
